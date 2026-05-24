"""TokenAuthentication with a TTL.

DRF's built-in `Token` model has no expiry. A stolen token is therefore
forever-valid until the legitimate user happens to log out. This
subclass enforces `ADMIN_TOKEN_TTL_SECONDS` against `token.created` and
rejects expired tokens with the same 401 envelope as missing-credentials,
which leaves the schema and the existing exception handler intact.

Rotation policy is enforced in `AdminLoginView`, not here: on login we
delete any prior token for the user and create a fresh one, so a leaked
older token becomes invalid as soon as the legitimate user re-authenticates.
True per-request rotation (rolling tokens via response header) is a
heavier change we've deferred -- the TTL + on-login rotation gives most
of the benefit at a fraction of the surface area.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ExpiringTokenAuthentication(TokenAuthentication):
    """`TokenAuthentication` that rejects tokens older than the TTL."""

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        ttl = getattr(settings, "ADMIN_TOKEN_TTL_SECONDS", 8 * 60 * 60)
        if ttl > 0 and token.created < timezone.now() - timedelta(seconds=ttl):
            raise AuthenticationFailed("Token has expired")
        return user, token


def token_expires_at(token) -> str | None:
    """ISO-8601 timestamp the token expires at, or None if TTL is disabled."""
    ttl = getattr(settings, "ADMIN_TOKEN_TTL_SECONDS", 8 * 60 * 60)
    if ttl <= 0:
        return None
    return (token.created + timedelta(seconds=ttl)).isoformat()
