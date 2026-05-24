"""
Response envelope. Every API response uses this shape:

    { "data": ..., "meta": {...} }            # success
    { "errors": [...], "meta": {...} }        # error

Inspired by JSON:API but deliberately simpler. Trades full spec compliance
for lower friction with DRF and clearer "full state on mutation" semantics.
"""

from uuid import uuid4

from apps.core.request_context import get_current_request_id


def _request_id(request) -> str:
    # Middleware sets this contextvar at the start of every HTTP request and
    # Celery signals set it for async work, so it's the single source of
    # truth. Fall back to the header / a fresh uuid only when called
    # outside that path (e.g. unit tests that hand-build a request).
    rid = get_current_request_id()
    if rid:
        return rid
    if request is not None:
        rid = request.META.get("HTTP_X_REQUEST_ID")
        if rid:
            return rid
    return str(uuid4())


def envelope(data=None, *, request=None, meta=None) -> dict:
    """Wrap a success payload in the standard envelope."""
    body = {
        "data": data,
        "meta": {
            "request_id": _request_id(request),
            "version": "v1",
        },
    }
    if meta:
        body["meta"].update(meta)
    return body


def error_envelope(*errors, request=None) -> dict:
    """Wrap one or more errors in the standard envelope.

    Each error should be a dict with at least `code` and `detail`.
    """
    cleaned = []
    for e in errors:
        if e is None:
            continue
        # Strip None values from source pointer
        if isinstance(e, dict) and e.get("source") is None:
            e = {k: v for k, v in e.items() if k != "source"}
        cleaned.append(e)
    return {
        "errors": cleaned,
        "meta": {
            "request_id": _request_id(request),
            "version": "v1",
        },
    }
