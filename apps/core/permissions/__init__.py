"""
Permission classes. Our "user" is a Customer from our domain (set by
CustomerAuthMiddleware), not Django's `auth.User`.

`AllowAny` is re-exported from DRF — the previous local copy was a
byte-identical reimplementation. Callers keep their existing
`from apps.core.permissions import AllowAny` imports.
"""

from rest_framework.permissions import AllowAny

from apps.core.permissions.is_authenticated_customer import IsAuthenticatedCustomer

__all__ = ["IsAuthenticatedCustomer", "AllowAny"]
