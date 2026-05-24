import logging

from django.conf import settings
from django.http import JsonResponse

from apps.core.middleware._exempt_paths import GLOBAL_EXEMPT_PATHS, is_exempt
from apps.core.responses import error_envelope
from apps.core.tenant_context import (
    reset_current_tenant_id,
    set_current_tenant_id,
)

log = logging.getLogger(__name__)


class TenantResolverMiddleware:
    """
    Resolves the tenant from the request's subdomain.

    Examples (with TENANT_DOMAIN_SUFFIX='acme.test'):
        store-a.acme.test     -> subdomain='store-a' -> Tenant.objects.get(subdomain='store-a')
        acme.test             -> no subdomain -> 400 unless path is exempt
        www.acme.test         -> reserved -> 400 unless path is exempt
        localhost             -> no subdomain -> 400 unless path is exempt
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if is_exempt(request, GLOBAL_EXEMPT_PATHS):
            return self.get_response(request)

        subdomain = self._extract_subdomain(request)

        if not subdomain:
            # Dev fallback: only when DEBUG and the override env is set. Logged once
            # at startup; not re-logged per request to avoid noise.
            fallback = getattr(settings, "DEV_DEFAULT_TENANT_SUBDOMAIN", "")
            if settings.DEBUG and fallback:
                subdomain = fallback
            else:
                return self._error("tenant_required", 400, request)

        # Import inside method to avoid AppRegistryNotReady at startup
        from apps.tenants.models import Tenant

        try:
            tenant = Tenant.all_objects.get(subdomain=subdomain, is_active=True)
        except Tenant.DoesNotExist:
            return self._error("tenant_not_found", 404, request)

        token = set_current_tenant_id(tenant.id)
        request.tenant = tenant
        try:
            return self.get_response(request)
        finally:
            reset_current_tenant_id(token)

    @staticmethod
    def _extract_subdomain(request) -> str | None:
        host = request.get_host().split(":")[0].lower()
        suffix = settings.TENANT_DOMAIN_SUFFIX.lower()

        # Strip the domain suffix to find the subdomain
        if host == suffix or not host.endswith(f".{suffix}"):
            return None

        candidate = host[: -len(suffix) - 1]  # strip ".acme.test"
        # Subdomain might itself contain dots (e.g. api.store-a.acme.test).
        # We take the leftmost label.
        candidate = candidate.split(".")[-1]

        if candidate in settings.TENANT_RESERVED_SUBDOMAINS:
            return None
        if not candidate:
            return None
        return candidate

    @staticmethod
    def _error(code, status, request):
        return JsonResponse(
            error_envelope({"code": code, "detail": code}, request=request),
            status=status,
        )
