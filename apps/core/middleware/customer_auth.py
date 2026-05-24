import logging

from django.http import JsonResponse

from apps.core.middleware._exempt_paths import (
    AUTH_EXEMPT_PATHS,
    GLOBAL_EXEMPT_PATHS,
    is_exempt,
)
from apps.core.responses import error_envelope

log = logging.getLogger(__name__)


class CustomerAuthMiddleware:
    """
    Resolve the authenticated Customer from the `X-Customer-Id` header.

    This is the application-internal half of authentication. In production,
    an upstream identity-aware proxy / API gateway (Cloudflare Access, an
    OIDC sidecar, Kong, etc.) validates the customer's token and sets
    `X-Customer-Id` after verification. The application trusts that header
    only because the path to it is trusted -- the gateway is responsible
    for rejecting forged headers from clients.

    Tenant cross-check is implicit: this middleware runs after
    TenantDBSessionMiddleware has set `app.current_tenant`, so the
    Customer.objects.get() below is filtered by Postgres RLS. A customer
    ID from another tenant returns a 404, not the wrong row.

    Skips:
    - GLOBAL_EXEMPT (admin, docs, schema, webhooks)
    - AUTH_EXEMPT (health)
    - Tests when TESTING_DISABLE_AUTH=True (see config/settings/test.py)
    """

    HEADER = "HTTP_X_CUSTOMER_ID"

    def __init__(self, get_response):
        from django.conf import settings

        self.get_response = get_response
        self.disable_for_tests = getattr(settings, "TESTING_DISABLE_AUTH", False)

    def __call__(self, request):
        if is_exempt(request, GLOBAL_EXEMPT_PATHS):
            return self.get_response(request)
        if is_exempt(request, AUTH_EXEMPT_PATHS):
            return self.get_response(request)
        if self.disable_for_tests:
            return self.get_response(request)

        customer_id = request.META.get(self.HEADER, "").strip()
        if not customer_id:
            return self._unauthorized("missing_customer_id", request)

        from apps.customers.models import Customer

        try:
            customer = Customer.objects.get(id=customer_id)
        except (Customer.DoesNotExist, ValueError):
            return self._unauthorized("customer_not_found", request)

        # Soft-deleted / blocked customers are treated as not-found so we
        # don't leak that the account exists. The tenant-admin sees the
        # is_active=False state explicitly via /admin/customers.
        if not customer.is_active:
            return self._unauthorized("customer_not_found", request)

        request.user = customer
        return self.get_response(request)

    @staticmethod
    def _unauthorized(code, request):
        return JsonResponse(
            error_envelope({"code": code, "detail": code}, request=request),
            status=401,
        )
