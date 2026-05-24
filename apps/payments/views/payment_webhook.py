import logging

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import AllowAny
from apps.payments.gateways import registry
from apps.payments.models import Payment
from apps.payments.services import build_credentials
from apps.payments.tasks import process_webhook_event

log = logging.getLogger(__name__)


class PaymentWebhookView(APIView):
    """Receive an asynchronous payment event from a gateway.

    `{gateway_name}` is the registered key (`mock`, `stripe`, ...).
    Exempt from both `CustomerAuthMiddleware` and tenant-subdomain
    resolution — gateways don't know our tenant subdomains, so this is
    one of the few endpoints that runs with no tenant context. We resolve
    the tenant by looking up the `Payment` row by `gateway_transaction_id`
    using the unscoped `all_objects` manager (the one place that's
    deliberate).

    Signature verification happens **before** any state mutation. An
    unknown gateway returns `404`, a malformed payload returns `400`, a
    forged or unsigned payload returns `401`, an event for an unknown
    transaction returns `404`. On success, the event is handed off to the
    `process_webhook_event` Celery task (which sets tenant context
    explicitly) and we return `202 Accepted` immediately.

    No request body schema is published here — bodies are gateway-native
    and validated by each gateway's `parse_webhook` / `verify_webhook`.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(summary="Receive a gateway webhook (no auth, no tenant)")
    def post(self, request, gateway_name):
        try:
            gateway = registry.get(gateway_name)
        except ValueError:
            return Response(status=status.HTTP_404_NOT_FOUND)

        raw_body = request.body
        signature = (
            request.META.get("HTTP_STRIPE_SIGNATURE")
            or request.META.get("HTTP_X_GATEWAY_SIGNATURE")
            or ""
        )

        try:
            event = gateway.parse_webhook(raw_body=raw_body)
        except Exception:
            log.exception("Failed to parse webhook")
            return Response(status=status.HTTP_400_BAD_REQUEST)

        # Resolve the tenant from the gateway_transaction_id.
        # We don't know the tenant yet, so this query must bypass both
        # the app-layer manager filter (`all_objects`) AND the database-
        # level RLS policy (`using("admin")` routes via the app_admin
        # connection that has BYPASSRLS). Without the admin alias the
        # app_user connection rejects the read because
        # `app.current_tenant` is unset → no rows visible. Same pattern
        # as `reconcile_pending_payments` in apps/payments/tasks.py.
        payment = (
            Payment.all_objects.using("admin")
            .select_related("gateway_config")
            .filter(gateway_transaction_id=event.gateway_transaction_id)
            .first()
        )
        if not payment:
            log.warning(
                "Unknown gateway_transaction_id in webhook: %s", event.gateway_transaction_id
            )
            return Response(status=status.HTTP_404_NOT_FOUND)

        credentials = build_credentials(payment.gateway_config)
        if not gateway.verify_webhook(
            credentials=credentials,
            raw_body=raw_body,
            signature_header=signature,
        ):
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        # Queue async processing. Tenant context set explicitly in the task.
        # gateway_name + event.event_id flow through so the task can dedupe
        # against ProcessedWebhookEvent before mutating anything.
        process_webhook_event.delay(
            str(payment.tenant_id),
            str(payment.id),
            event.event_type,
            event.status.value,
            event.raw_payload,
            gateway_name,
            event.event_id,
        )

        return Response(status=status.HTTP_202_ACCEPTED)
