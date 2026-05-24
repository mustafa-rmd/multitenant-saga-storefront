"""
PaymentService -- orchestrates the gateway abstraction.

Critical pattern: we INSERT the Payment row in PENDING status BEFORE calling
the gateway. The unique constraint on `idempotency_key` makes "outage =
double charge" impossible; reconciliation catches rows stuck in PENDING
with no `gateway_transaction_id` and asks the gateway "what happened?"
to fill in the truth.

Transactional shape: we deliberately do NOT wrap this whole method in
`@transaction.atomic`. The gateway HTTP call must not run inside an open
savepoint -- that would hold locks (and the Postgres backend) across a
multi-second network call. Instead, each DB touch opens its own short
atomic block; the gateway call sits between them with no open block.

Caveat (documented honestly): under the project's `ATOMIC_REQUESTS=True`
setting, every HTTP request is itself wrapped in one big transaction by
Django, so the entire checkout saga -- including this method -- still
runs inside the request transaction. True per-phase durability would
require marking the checkout view `@non_atomic_requests` and committing
explicitly between saga phases. That's a larger refactor than this
change; for now, the structure here is correct for the day the saga is
moved off of request-wrapping (e.g. for an async/Celery checkout path).
"""

import logging
from decimal import Decimal
from uuid import UUID

from django.conf import settings
from django.db import transaction

from apps.core.exceptions import (
    GatewayNotConfigured,
    GatewayUnsupportedCurrency,
    PaymentFailed,
)
from apps.core.tenant_context import get_current_tenant_id
from apps.payments.gateways import registry
from apps.payments.gateways.base import GatewayCredentials, PaymentStatus
from apps.payments.models import Payment, PaymentGatewayConfig, PaymentMethod
from apps.payments.models.gateway_name import GatewayName

log = logging.getLogger(__name__)


def resolve_gateway_config(*, gateway_name: str) -> PaymentGatewayConfig:
    """Resolve an active gateway config for the current tenant.

    Single chokepoint for the two checks every gateway lookup needs:
      * The `mock` gateway is gated by `PAYMENTS_ALLOW_MOCK_GATEWAY` so a
        leftover `mock` config row in production can't be used to "pay".
      * The config must exist AND be `is_active=True`. We raise
        `GatewayNotConfigured` (409) rather than letting a bare ORM
        `DoesNotExist` bubble as a 500.

    Tenant scoping is handled by the default manager (RLS + ContextVar),
    so this never needs to be told which tenant to look in.
    """
    if gateway_name == GatewayName.MOCK and not settings.PAYMENTS_ALLOW_MOCK_GATEWAY:
        raise GatewayNotConfigured(f"Gateway '{gateway_name}' is not available in this environment")
    try:
        return PaymentGatewayConfig.objects.get(
            gateway_name=gateway_name,
            is_active=True,
        )
    except PaymentGatewayConfig.DoesNotExist as e:
        raise GatewayNotConfigured(
            f"Gateway '{gateway_name}' is not configured for this tenant"
        ) from e


class PaymentService:
    @staticmethod
    def authorize_payment(
        *,
        order_id: UUID,
        payment_method_id: UUID,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
        metadata: dict | None = None,
    ) -> Payment:
        """Reserve funds via the configured gateway. Returns the Payment row.

        Three steps with the gateway call OUTSIDE any atomic block:
          1. Persist PENDING row (short atomic block).
          2. Call the gateway (no open transaction).
          3. Record the result (short atomic block).
        """
        payment_method = PaymentMethod.objects.select_related("gateway_config").get(
            id=payment_method_id
        )
        gateway_config = payment_method.gateway_config

        # Re-validate the gateway at checkout time. The PaymentMethod row
        # holds a hard FK to a specific config, but an admin may have
        # deactivated that config since the method was saved -- and the mock
        # gate may have been flipped off as the environment was promoted.
        # Re-resolving by name picks up either change.
        gateway_config = resolve_gateway_config(gateway_name=gateway_config.gateway_name)

        gateway = registry.get(gateway_config.gateway_name)
        credentials = build_credentials(gateway_config)

        if not gateway.supports_currency(currency):
            raise GatewayUnsupportedCurrency(gateway=gateway.name, currency=currency)

        # --- Step 1: PENDING row -----------------------------------------
        payment = _create_pending_payment(
            order_id=order_id,
            gateway_config_id=gateway_config.id,
            amount=amount,
            currency=currency,
            idempotency_key=idempotency_key,
        )

        # --- Step 2: gateway call, no open atomic block ------------------
        try:
            intent = gateway.authorize(
                credentials=credentials,
                amount=amount,
                currency=currency,
                payment_method_token=payment_method.token,
                idempotency_key=idempotency_key,
                metadata=metadata or {},
            )
        except Exception as exc:
            log.exception("Gateway authorize() raised")
            _record_payment_error(payment.id, str(exc))
            raise PaymentFailed(detail=f"Gateway error: {exc}") from exc

        # --- Step 3: result write ----------------------------------------
        gateway_response = dict(intent.raw_response or {})
        if intent.next_action:
            gateway_response["next_action"] = intent.next_action

        new_status = map_gateway_status(intent.status)
        _record_payment_result(
            payment_id=payment.id,
            gateway_transaction_id=intent.gateway_transaction_id,
            status=new_status,
            gateway_response=gateway_response,
        )

        # Reflect the result on the in-memory object so the caller can read
        # it without a re-fetch.
        payment.gateway_transaction_id = intent.gateway_transaction_id
        payment.status = new_status
        payment.gateway_response = gateway_response

        if intent.status == PaymentStatus.FAILED:
            raw = intent.raw_response or {}
            raise PaymentFailed(
                detail=raw.get("failure_message", "Payment declined"),
                gateway_code=raw.get("failure_code"),
            )

        return payment

    @staticmethod
    def create_invoice_pending_payment(
        *,
        order_id: UUID,
        amount: Decimal,
        currency: str,
        idempotency_key: str,
    ) -> Payment:
        """Record a PO/invoiced payment without calling any gateway.

        Used by the checkout saga when the cart's selected payment method
        is `purchase_order`. The Payment row is created in
        `INVOICE_PENDING` and is flipped to `CAPTURED` by an admin via
        `POST /admin/orders/{id}/mark-paid` once the wire/cheque clears.

        Same idempotency-key uniqueness as `authorize_payment`, so a
        client retry of the same checkout cannot produce two rows.
        """
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise RuntimeError("create_invoice_pending_payment called without tenant context")

        with transaction.atomic():
            return Payment.objects.create(
                tenant_id=tenant_id,
                order_id=order_id,
                gateway_config=None,
                status=Payment.Status.INVOICE_PENDING,
                amount=amount,
                currency=currency,
                idempotency_key=idempotency_key,
            )

    @staticmethod
    def mark_invoice_paid(*, payment_id: UUID, reference: str = "") -> Payment:
        """Flip an INVOICE_PENDING payment to CAPTURED. Idempotent.

        Tenant-admin marks a PO order paid once the invoice clears. The
        update is conditional on the current status so a concurrent
        admin click doesn't double-fire.
        """
        with transaction.atomic():
            payment = Payment.objects.select_for_update().get(id=payment_id)
            if payment.status == Payment.Status.CAPTURED:
                return payment  # idempotent
            if payment.status != Payment.Status.INVOICE_PENDING:
                raise PaymentFailed(
                    detail=f"Cannot mark paid: payment is in status {payment.status}"
                )
            response = dict(payment.gateway_response or {})
            response["marked_paid_reference"] = reference
            payment.status = Payment.Status.CAPTURED
            payment.gateway_response = response
            payment.save(update_fields=["status", "gateway_response", "updated_at"])
            return payment

    @staticmethod
    def capture_payment(*, payment_id: UUID) -> Payment:
        """Move an AUTHORIZED payment to CAPTURED.

        Same shape as authorize_payment: read row, call gateway with no open
        atomic block, then write the result back with a status guard in the
        WHERE clause so a concurrent webhook can't double-apply.
        """
        payment = Payment.objects.select_related("gateway_config").get(id=payment_id)
        if payment.status == Payment.Status.CAPTURED:
            return payment  # idempotent

        if payment.status != Payment.Status.AUTHORIZED:
            raise PaymentFailed(detail=f"Cannot capture payment in status {payment.status}")

        gateway = registry.get(payment.gateway_config.gateway_name)
        credentials = build_credentials(payment.gateway_config)

        intent = gateway.capture(
            credentials=credentials,
            gateway_transaction_id=payment.gateway_transaction_id,
            idempotency_key=f"{payment.idempotency_key}:capture",
            amount=payment.amount,
        )

        new_status = map_gateway_status(intent.status)
        with transaction.atomic():
            updated = Payment.objects.filter(
                id=payment.id,
                status=Payment.Status.AUTHORIZED,  # guard against webhook race
            ).update(
                status=new_status,
                gateway_response=intent.raw_response or {},
            )

        if updated == 0:
            # A webhook beat us to it. Re-read and return whatever the row
            # now says -- capture is idempotent from the gateway's side too.
            payment = Payment.objects.get(id=payment.id)
        else:
            payment.status = new_status
            payment.gateway_response = intent.raw_response or {}
        return payment

    @staticmethod
    def refund_payment(
        *,
        payment_id: UUID,
        amount: Decimal | None = None,
        reason: str | None = None,
    ) -> Payment:
        """Same shape as capture_payment: read, network call, conditional write."""
        payment = Payment.objects.select_related("gateway_config").get(id=payment_id)
        if payment.status != Payment.Status.CAPTURED:
            raise PaymentFailed(detail=f"Cannot refund payment in status {payment.status}")
        if payment.gateway_config_id is None:
            # PO payments aren't refundable via the gateway path — the
            # original "payment" was a wire/cheque against an invoice.
            # Refund flow there is out-of-band (issue a credit note).
            raise PaymentFailed(detail="Cannot refund a purchase-order payment via gateway")

        gateway = registry.get(payment.gateway_config.gateway_name)
        credentials = build_credentials(payment.gateway_config)

        intent = gateway.refund(
            credentials=credentials,
            gateway_transaction_id=payment.gateway_transaction_id,
            idempotency_key=f"{payment.idempotency_key}:refund:{amount or 'full'}",
            amount=amount,
            reason=reason,
        )

        new_status = map_gateway_status(intent.status)
        with transaction.atomic():
            Payment.objects.filter(id=payment.id).update(
                status=new_status,
                gateway_response=intent.raw_response or {},
            )
        payment.status = new_status
        payment.gateway_response = intent.raw_response or {}
        return payment


# ---------------------------------------------------------------------------
# Internal helpers -- short atomic blocks isolating the gateway call.
# ---------------------------------------------------------------------------


def _create_pending_payment(
    *,
    order_id: UUID,
    gateway_config_id: UUID,
    amount: Decimal,
    currency: str,
    idempotency_key: str,
) -> Payment:
    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        raise RuntimeError("authorize_payment called without tenant context")

    with transaction.atomic():
        return Payment.objects.create(
            tenant_id=tenant_id,
            order_id=order_id,
            gateway_config_id=gateway_config_id,
            status=Payment.Status.PENDING,
            amount=amount,
            currency=currency,
            idempotency_key=idempotency_key,
        )


def _record_payment_result(
    *,
    payment_id: UUID,
    gateway_transaction_id: str,
    status: str,
    gateway_response: dict,
) -> None:
    with transaction.atomic():
        Payment.objects.filter(id=payment_id).update(
            gateway_transaction_id=gateway_transaction_id,
            status=status,
            gateway_response=gateway_response,
        )


def _record_payment_error(payment_id: UUID, error_message: str) -> None:
    # Merge so any prior gateway_response context (set elsewhere before
    # the exception) is preserved alongside the exception note.
    with transaction.atomic():
        payment = Payment.objects.filter(id=payment_id).only("gateway_response").first()
        existing = (payment.gateway_response if payment else None) or {}
        Payment.objects.filter(id=payment_id).update(
            gateway_response={**existing, "exception": error_message},
        )


def build_credentials(config: PaymentGatewayConfig) -> GatewayCredentials:
    """Translate the stored credentials JSONB into the typed dataclass.

    In production this should decrypt the JSONB using KMS / Django's
    signing keys. For the POC it's plaintext.
    """
    raw = config.credentials or {}
    return GatewayCredentials(
        public_key=raw.get("public_key"),
        secret_key=raw.get("secret_key"),
        webhook_secret=raw.get("webhook_secret"),
        extra=raw.get("extra"),
    )


def map_gateway_status(status: PaymentStatus) -> str:
    return {
        PaymentStatus.PENDING: Payment.Status.PENDING,
        PaymentStatus.AUTHORIZED: Payment.Status.AUTHORIZED,
        PaymentStatus.CAPTURED: Payment.Status.CAPTURED,
        PaymentStatus.FAILED: Payment.Status.FAILED,
        PaymentStatus.REFUNDED: Payment.Status.REFUNDED,
        PaymentStatus.CANCELLED: Payment.Status.CANCELLED,
    }[status]
