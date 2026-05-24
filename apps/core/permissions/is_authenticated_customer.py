from rest_framework.permissions import BasePermission


class IsAuthenticatedCustomer(BasePermission):
    """Require an authenticated customer (set by CustomerAuthMiddleware)."""

    message = "Authentication credentials were not provided."

    def has_permission(self, request, view):
        from apps.customers.models import Customer

        user = getattr(request, "user", None)
        return isinstance(user, Customer)
