"""
Middleware stack for tenant isolation and authentication.

Execution order (top to bottom of MIDDLEWARE setting):

    1. TenantResolverMiddleware
       Parses subdomain, looks up Tenant, sets the contextvar and
       attaches request.tenant.

    2. TenantDBSessionMiddleware
       Runs `SET LOCAL app.current_tenant = '<uuid>'` on the request's
       DB connection so Postgres RLS policies fire.

    3. CustomerAuthMiddleware
       Reads X-Customer-Id (set by the upstream identity proxy in
       production) and resolves the local Customer. Runs after the DB
       session middleware so the Customer lookup is itself RLS-scoped --
       a customer ID from the wrong tenant returns 404.

Together this gives us two-layer tenant isolation:
    - Application layer: TenantManager filters all queries by contextvar
    - Database layer: RLS policies refuse to return rows for the wrong tenant

Either layer alone would mostly work. Together, a bug in one can't leak data.
"""

from apps.core.middleware.camel_case import CamelCaseMiddleware
from apps.core.middleware.customer_auth import CustomerAuthMiddleware
from apps.core.middleware.request_id import RequestIdMiddleware
from apps.core.middleware.tenant_db_session import TenantDBSessionMiddleware
from apps.core.middleware.tenant_resolver import TenantResolverMiddleware

__all__ = [
    "RequestIdMiddleware",
    "TenantResolverMiddleware",
    "TenantDBSessionMiddleware",
    "CustomerAuthMiddleware",
    "CamelCaseMiddleware",
]
