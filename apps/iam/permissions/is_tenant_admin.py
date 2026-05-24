from django.contrib.auth import get_user_model
from rest_framework.permissions import BasePermission

from apps.iam.models import Role, TenantMembership

User = get_user_model()


class IsTenantAdmin(BasePermission):
    """Require a Django User with a TENANT_ADMIN membership for `request.tenant`.

    Superusers are accepted as tenant-admin on any resolved tenant -- they
    are platform staff and need to be able to step into a tenant for
    support without an explicit membership.

    The membership check is a live DB query on every request (no caching
    in the token). Membership revocation takes effect on the next request.
    """

    message = "Tenant admin credentials required."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not (isinstance(user, User) and user.is_authenticated):
            return False
        tenant = getattr(request, "tenant", None)
        if tenant is None:
            return False
        if user.is_superuser:
            return True
        return TenantMembership.objects.filter(
            user=user,
            tenant_id=tenant.id,
            role=Role.TENANT_ADMIN,
        ).exists()
