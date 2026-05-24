"""drf-spectacular postprocessing hooks.

CamelCaseMiddleware rewrites every JSON request/response body between
snake_case (Python) and camelCase (wire). drf-spectacular generates the
OpenAPI schema from the raw serializer field names, so without a hook
Swagger displays snake_case while the actual wire is camelCase. This
hook walks the generated schema and camelizes property names + required
arrays so Swagger matches what clients actually send and receive.

Path/query parameters are intentionally left alone — path params have to
match the URL pattern in urls.py, and query params aren't touched by the
camelCase middleware either.
"""

from apps.core.middleware.camel_case import _to_camel


def _camelize_schema(node):
    if isinstance(node, dict):
        if "properties" in node and isinstance(node["properties"], dict):
            node["properties"] = {
                _to_camel(k): _camelize_schema(v) for k, v in node["properties"].items()
            }
        if "required" in node and isinstance(node["required"], list):
            node["required"] = [_to_camel(k) if isinstance(k, str) else k for k in node["required"]]
        for key in ("items", "additionalProperties"):
            if key in node and isinstance(node[key], dict):
                _camelize_schema(node[key])
        for key in ("oneOf", "anyOf", "allOf"):
            if key in node and isinstance(node[key], list):
                for sub in node[key]:
                    _camelize_schema(sub)
    return node


def camelize_schema_properties(result, generator, request, public):
    """Rewrite snake_case schema properties as camelCase to match the wire."""
    schemas = result.get("components", {}).get("schemas", {})
    for schema in schemas.values():
        _camelize_schema(schema)
    return result
