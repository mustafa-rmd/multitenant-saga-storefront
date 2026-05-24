"""
DRF authentication that adopts the user already set on the underlying Django
request by CustomerAuthMiddleware.

Why this exists: DRF's `Request.user` is a lazy property that runs the
authentication classes on first access. With an empty
DEFAULT_AUTHENTICATION_CLASSES, DRF falls back to AnonymousUser regardless of
what middleware set on the underlying Django request. This class bridges the
two: if the middleware already authenticated a Customer, return it.
"""

from rest_framework.authentication import BaseAuthentication


class MiddlewareCustomerAuthentication(BaseAuthentication):
    def authenticate(self, request):
        from apps.customers.models import Customer

        user = getattr(request._request, "user", None)
        if isinstance(user, Customer):
            return (user, None)
        return None
