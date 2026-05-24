import uuid

from django.conf import settings
from django.db import models

from apps.iam.models.role import Role


class TenantMembership(models.Model):
    """Binds a Django User to a Tenant with a role.

    Lives in the admin schema -- this table is NOT tenant-scoped (no RLS
    policy, no `tenant_id` filter via TenantManager). Platform-admin is
    represented by `User.is_superuser=True`; superusers carry zero
    memberships. Tenant-admin = one membership row per tenant they admin.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tenant_memberships",
    )
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.TENANT_ADMIN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "iam_tenantmembership"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "tenant"],
                name="uniq_membership_per_user_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "role"]),
        ]

    def __str__(self):
        return f"{self.user_id} -> {self.tenant_id} ({self.role})"
