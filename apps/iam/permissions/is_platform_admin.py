from django.contrib.auth import get_user_model
from rest_framework.permissions import BasePermission

User = get_user_model()


class IsPlatformAdmin(BasePermission):
    """Require an authenticated Django User with is_superuser=True.

    Explicitly checks `isinstance(user, User)` because the project's other
    auth class (`MiddlewareCustomerAuthentication`) sets `request.user` to
    a `Customer` instance, which has no `is_superuser` attribute -- but a
    plain `truthy(user) and getattr(user, 'is_superuser', False)` would
    silently fall through if a future refactor added that attribute on
    Customer. Fail closed on type, not on attribute presence.
    """

    message = "Platform admin credentials required."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return isinstance(user, User) and user.is_authenticated and user.is_superuser
