"""
Tenant model.

Tenants are NOT themselves tenant-scoped (obviously) -- they're the root.
We expose both `objects` (the default) and `all_objects` for symmetry
with TenantScopedModel, but they behave identically here.

`order_sequence_name` is used to drive per-tenant order numbering via
Postgres sequences -- see apps/orders/services for usage.
"""

import uuid

from django.db import models


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    subdomain = models.SlugField(max_length=63, unique=True, db_index=True)
    default_currency = models.CharField(max_length=3, default="SAR")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # For symmetry with TenantScopedModel
    objects = models.Manager()
    all_objects = models.Manager()

    class Meta:
        db_table = "tenants_tenant"
        ordering = ["subdomain"]

    def __str__(self):
        return f"{self.name} ({self.subdomain})"

    @property
    def order_sequence_name(self) -> str:
        """Name of the per-tenant Postgres sequence for order numbers."""
        # UUIDs contain hyphens which are invalid in identifiers, so we underscore
        safe_id = str(self.id).replace("-", "_")
        return f"order_number_seq_{safe_id}"
