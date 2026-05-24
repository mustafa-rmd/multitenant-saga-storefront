"""Translate JSON keys between camelCase (wire) and snake_case (Python).

Python and DRF use snake_case for attribute names and serializer fields.
JS/Swift/Kotlin clients prefer camelCase. This middleware bridges the
two so neither side has to compromise:

    Request  (camelCase JSON)  -> decamelize keys -> serializers see snake_case
    Response (snake_case dict) -> camelize keys   -> client receives camelCase

Only dictionary KEYS are transformed. String values are left intact -
error codes like "insufficient_stock" are enum-like identifiers, not
field names, and must remain stable across the wire.

Path-exempt (gateway payloads and OpenAPI docs are NOT transformed):

    /admin/                 HTML, no JSON to transform
    /api/v1/docs/           Swagger UI assets
    /api/v1/schema/         OpenAPI document - already uses its own conventions
    /api/v1/webhooks/       Gateway-native bodies (Stripe sends snake_case)

The exemption list is `CAMEL_CASE_EXEMPT_PATHS` and is intentionally
narrower than `GLOBAL_EXEMPT_PATHS` -- the admin REST surface skips
tenant resolution but still needs camelCase JSON for its API clients.
"""

import json
import re

from apps.core.middleware._exempt_paths import CAMEL_CASE_EXEMPT_PATHS, is_exempt

_TO_CAMEL_RE = re.compile(r"_([a-z0-9])")
_TO_SNAKE_RE = re.compile(r"(?<=[a-z0-9])([A-Z])")


def _to_camel(key: str) -> str:
    return _TO_CAMEL_RE.sub(lambda m: m.group(1).upper(), key)


def _to_snake(key: str) -> str:
    return _TO_SNAKE_RE.sub(r"_\1", key).lower()


def _transform_keys(obj, fn):
    if isinstance(obj, dict):
        return {
            (fn(k) if isinstance(k, str) else k): _transform_keys(v, fn) for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_transform_keys(item, fn) for item in obj]
    return obj


class CamelCaseMiddleware:
    """Wire-format = camelCase, internal = snake_case."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        exempt = is_exempt(request, CAMEL_CASE_EXEMPT_PATHS)
        if not exempt:
            self._decamelize_request(request)

        response = self.get_response(request)

        if not exempt:
            self._camelize_response(response)

        return response

    @staticmethod
    def _decamelize_request(request):
        if not request.body:
            return
        ctype = request.META.get("CONTENT_TYPE", "")
        if "application/json" not in ctype:
            return
        try:
            payload = json.loads(request.body)
        except (ValueError, UnicodeDecodeError):
            return
        transformed = _transform_keys(payload, _to_snake)
        # Replace the cached body so DRF parsers see the snake_case version.
        request._body = json.dumps(transformed).encode("utf-8")

    @staticmethod
    def _camelize_response(response):
        if not getattr(response, "content", None):
            return
        ctype = response.get("Content-Type", "")
        if "application/json" not in ctype:
            return
        try:
            payload = json.loads(response.content)
        except (ValueError, UnicodeDecodeError):
            return
        transformed = _transform_keys(payload, _to_camel)
        response.content = json.dumps(transformed).encode("utf-8")
        if response.has_header("Content-Length"):
            response["Content-Length"] = str(len(response.content))
