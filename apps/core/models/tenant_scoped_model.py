import uuid

from django.db import models

from apps.core.models.tenant_manager import TenantManager
from apps.core.models.unscoped_manager import UnscopedManager
from apps.core.tenant_context import get_current_tenant_id


class TenantScopedModel(models.Model):
    """Abstract base for any model that belongs to a single tenant."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="+",
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = UnscopedManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.tenant_id:
            tenant_id = get_current_tenant_id()
            if tenant_id is None:
                raise RuntimeError(
                    f"Cannot save {type(self).__name__} without tenant context. "
                    "Set tenant via middleware or `with tenant_context(...)`."
                )
            self.tenant_id = tenant_id
        super().save(*args, **kwargs)
