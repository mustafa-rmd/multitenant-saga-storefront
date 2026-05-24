"""Path-exemption tables and helper, shared by the middleware classes.

Three distinct exemption tiers, intentionally separate:

* GLOBAL_EXEMPT_PATHS  -- skip tenant resolution AND customer auth.
* AUTH_EXEMPT_PATHS    -- skip customer auth only (tenant still resolved).
* CAMEL_CASE_EXEMPT    -- skip JSON-key camel/snake transformation (Swagger,
                          gateway-native webhook bodies, Django HTML admin).

GLOBAL and CAMEL_CASE used to be the same list. They were split so that
the admin REST surface (`/api/v1/admin/platform/`, `/api/v1/admin/auth/`)
could skip tenant resolution without also losing the wire-format
transformation that admin JSON clients expect.
"""

GLOBAL_EXEMPT_PATHS = (
    "/admin/",
    "/api/v1/docs/",
    "/api/v1/schema/",
    "/api/v1/webhooks/",
    # The dashboard is a static HTML page; it doesn't need a tenant
    # resolved to render. Its JS hits /api/v1/admin/* with the Host
    # header that tenant-admin endpoints already expect.
    "/dashboard/",
    # Platform-admin operates across tenants and runs under the reserved
    # `admin` subdomain -- subdomain-based tenant resolution doesn't apply.
    "/api/v1/admin/platform/",
    # /admin/auth/ (login, logout, me) is host-independent: an admin must be
    # able to log in regardless of which subdomain Swagger UI happens to be
    # served from.
    "/api/v1/admin/auth/",
)

# Skip customer auth, keep tenant resolution. /api/v1/admin/ covers the
# tenant-admin REST surface (products, coupons, gateway config, orders),
# which lives under each tenant's subdomain and uses token auth instead
# of X-Customer-Id.
AUTH_EXEMPT_PATHS = (
    "/api/v1/health",
    "/api/v1/admin/",
)

# Skip JSON key transformation. These responses are either HTML (Django
# admin, Swagger UI) or have their own wire conventions (OpenAPI schema,
# gateway webhook payloads that must stay native).
CAMEL_CASE_EXEMPT_PATHS = (
    "/admin/",
    "/api/v1/docs/",
    "/api/v1/schema/",
    "/api/v1/webhooks/",
    "/dashboard/",
)


def is_exempt(request, paths):
    return any(request.path.startswith(p) for p in paths)
