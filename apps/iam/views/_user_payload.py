"""Shared helper for serializing the authenticated admin user.

Returned by /auth/login and /auth/me. Kept here to keep both views
honest -- the shape never drifts between the two endpoints.
"""

from apps.iam.models import TenantMembership


def serialize_user(user) -> dict:
    memberships = TenantMembership.objects.filter(user=user).select_related("tenant")
    return {
        "id": user.id,
        "email": user.email,
        "is_superuser": user.is_superuser,
        "memberships": [
            {
                "tenant_id": str(m.tenant_id),
                "tenant_subdomain": m.tenant.subdomain,
                "role": m.role,
            }
            for m in memberships
        ],
    }
