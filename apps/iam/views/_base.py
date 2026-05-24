"""Shared base classes for admin views.

Tenant-admin views use the default DB connection (`app_user`, RLS-enforced)
so cross-tenant rows are physically unreachable. Platform-admin views use
the `admin` DB connection (`app_admin`, BYPASSRLS) and must therefore
filter tenant scope explicitly -- the `using_admin_db()` helper makes
the intent loud at every call site.
"""

from rest_framework.generics import GenericAPIView

from apps.iam.authentication import ExpiringTokenAuthentication
from apps.iam.permissions import IsPlatformAdmin, IsTenantAdmin

ADMIN_DB_ALIAS = "admin"


class TenantAdminAPIView(GenericAPIView):
    """Base for views that act within a single tenant.

    `request.tenant` is set by `TenantResolverMiddleware` (subdomain
    resolution) and `app.current_tenant` is set on the DB session by
    `TenantDBSessionMiddleware` -- both still run because `/api/v1/admin/`
    is only in `AUTH_EXEMPT_PATHS`, not `GLOBAL_EXEMPT_PATHS`.

    Auth: `ExpiringTokenAuthentication` enforces `ADMIN_TOKEN_TTL_SECONDS`.
    """

    authentication_classes = [ExpiringTokenAuthentication]
    permission_classes = [IsTenantAdmin]


class PlatformAdminAPIView(GenericAPIView):
    """Base for cross-tenant ops. Routes ORM through the admin DB alias.

    Subclasses MUST use `Model.objects.using(ADMIN_DB_ALIAS)...` (or the
    Tenant `all_objects` manager) and MUST apply tenant scoping where
    appropriate -- BYPASSRLS will happily return every tenant's rows.

    Auth: `ExpiringTokenAuthentication` enforces `ADMIN_TOKEN_TTL_SECONDS`.
    """

    authentication_classes = [ExpiringTokenAuthentication]
    permission_classes = [IsPlatformAdmin]
