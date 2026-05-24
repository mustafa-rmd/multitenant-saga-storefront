"""Rate limiters for the admin login endpoint.

Two independent throttles applied to `POST /admin/auth/login`:

  * `LoginIpThrottle`    — caps requests per client IP. Catches the
    "single attacker, many emails" pattern (credential stuffing,
    enumeration).
  * `LoginEmailThrottle` — caps requests per *target* email address
    (read from the request body, not the authenticated user).
    Catches the "many distributed attackers, one target" pattern.

Both are applied at the same time -- DRF evaluates all
`throttle_classes` and the request is rejected if any of them deny.
Rates default to liberal values so the Bun suite (which logs in many
admins in quick succession across parallel files) doesn't trip them;
production deployments should override the env vars to something
tight, e.g. 10/min IP and 5/min email.

Cache backend: uses Django's default cache framework. In dev that's
LocMem (per-process, fine for one runserver). In production point
`CACHES['default']` at Redis so the limits hold across workers.
"""

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class LoginIpThrottle(SimpleRateThrottle):
    """Throttle on the requesting IP."""

    scope = "login_ip"

    def get_rate(self) -> str:
        return getattr(settings, "ADMIN_LOGIN_THROTTLE_RATE_IP", "60/min")

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class LoginEmailThrottle(SimpleRateThrottle):
    """Throttle on the `email` field of the request body.

    Reads email from `request.data` (already JSON-parsed by DRF). Missing
    or non-string emails are bucketed under a placeholder so a flood of
    malformed bodies can't bypass the IP throttle's bucket.
    """

    scope = "login_email"

    def get_rate(self) -> str:
        return getattr(settings, "ADMIN_LOGIN_THROTTLE_RATE_EMAIL", "30/min")

    def get_cache_key(self, request, view):
        raw = request.data.get("email") if hasattr(request, "data") else None
        ident = raw.strip().lower() if isinstance(raw, str) and raw.strip() else "__missing__"
        return self.cache_format % {"scope": self.scope, "ident": ident}
