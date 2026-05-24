from django.db import models

from apps.core.tenant_context import get_current_tenant_id


class TenantManager(models.Manager):
    """Auto-scopes queries by the current tenant from contextvars.

    If no tenant is set in context, returns an empty queryset (fail closed).
    This protects against accidentally running an unscoped query in code
    that forgot to enter a tenant context.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            # Fail closed: no tenant = no rows.
            # If you really need cross-tenant access, use `all_objects`.
            return qs.none()
        return qs.filter(tenant_id=tenant_id)
