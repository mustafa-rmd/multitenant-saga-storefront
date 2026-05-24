"""Async payment tasks: webhook ingestion + PENDING reconciliation sweep."""

import logging
from datetime import timedelta

from celery import shared_task
from django.db import IntegrityError, connection, transaction
from django.db.models import F
from django.utils import timezone

from apps.carts.models import Cart
from apps.catalog.models import Product
from apps.core.celery_helpers import DurableTask, TenantAwareTask
from apps.core.tenant_context import reset_current_tenant_id, set_current_tenant_id
from apps.orders.models import (
    InventoryReservation,
    Order,
    ReservationStatus,
)
from apps.orders.tasks import generate_invoice
from apps.payments.gateways import registry
from apps.payments.gateways.base import (
    PaymentStatus as GatewayStatus,
)  # gateway enum, not Payment.Status
from apps.payments.models import Payment, ProcessedWebhookEvent
from apps.payments.services import build_credentials, map_gateway_status

log = logging.getLogger(__name__)


@shared_task(
    base=TenantAwareTask,
    bind=True,
    autoretry_for=(Exception,),
    max_retries=5,
    default_retry_delay=30,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def process_webhook_event(
    self,
    tenant_id: str,
    payment_id: str,
    event_type: str,
    new_status: str,
    raw_payload: dict,
    gateway_name: str,
    event_id: str,
):
    """Apply a webhook event to a Payment and propagate to the Order.

    Idempotency: the FIRST statement inside the atomic block inserts a row
    into ProcessedWebhookEvent. The UNIQUE constraint on (gateway_name,
    event_id) means a redelivered event raises IntegrityError, which rolls
    the whole transaction back -- nothing mutated, no double charge.

    Dedupe row + mutations live in the SAME transaction on purpose: if the
    mutation half fails, the dedupe row rolls back too, so the next retry
    can still apply the event. Inserting the dedupe row in a separate
    autocommit transaction would lock out retries forever on the first
    transient mutation failure.

    Without this guard, Stripe's aggressive retries (any 5xx, any timeout,
    any slow response) would double-decrement stock via
    _commit_reservations_for_order.
    """
    try:
        with transaction.atomic():
            # --- Dedupe gate: first write in the transaction --------------
            ProcessedWebhookEvent.objects.create(
                gateway_name=gateway_name,
                event_id=event_id,
                event_type=event_type,
            )

            # --- Mutation path --------------------------------------------
            payment = Payment.objects.select_for_update().get(id=payment_id)
            payment.status = new_status
            payment.gateway_response = raw_payload
            payment.save(update_fields=["status", "gateway_response", "updated_at"])

            order = Order.objects.select_for_update().get(id=payment.order_id)

            if event_type == "payment.captured":
                _apply_order_paid(order)
            elif event_type in ("payment.failed", "payment.cancelled"):
                _apply_order_cancelled(order)
            elif event_type == "payment.refunded":
                order.status = Order.Status.REFUNDED
                order.save(update_fields=["status", "updated_at"])
            else:
                log.warning("Unhandled webhook event type: %s", event_type)
    except IntegrityError:
        log.info(
            "Duplicate webhook ignored: gateway=%s event_id=%s",
            gateway_name,
            event_id,
        )


def _enqueue_invoice_on_commit(order: Order) -> None:
    tenant_id_str = str(order.tenant_id)
    order_id_str = str(order.id)
    transaction.on_commit(lambda: generate_invoice.delay(tenant_id_str, order_id_str))


def _commit_reservations_for_order(order: Order) -> None:
    reservations = InventoryReservation.objects.select_for_update().filter(
        order=order,
        status=ReservationStatus.ACTIVE,
    )
    for res in reservations:
        Product.objects.filter(id=res.product_id).update(
            stock_quantity=F("stock_quantity") - res.quantity,
            reserved_quantity=F("reserved_quantity") - res.quantity,
        )
        res.status = ReservationStatus.COMMITTED
        res.save(update_fields=["status", "updated_at"])


def _release_reservations_for_order(order: Order) -> None:
    reservations = InventoryReservation.objects.select_for_update().filter(
        order=order,
        status=ReservationStatus.ACTIVE,
    )
    for res in reservations:
        Product.objects.filter(id=res.product_id).update(
            reserved_quantity=F("reserved_quantity") - res.quantity,
        )
        res.status = ReservationStatus.RELEASED
        res.save(update_fields=["status", "updated_at"])


def _revert_cart_if_checking_out(order: Order) -> None:
    """If the order's cart is still wedged in CHECKING_OUT, flip it back to
    ACTIVE. Otherwise the customer's cart stays unusable after an async
    failure (e.g. abandoned 3DS → payment.failed webhook)."""
    if order.cart_id:
        Cart.all_objects.filter(id=order.cart_id, status=Cart.Status.CHECKING_OUT).update(
            status=Cart.Status.ACTIVE
        )


def _apply_order_paid(order: Order) -> None:
    """Shared paid-path for a locked Order. Idempotent.

    Used by both the webhook handler (which already holds the row lock)
    and the reconcile sweep. Skips work if the order is already PAID.
    """
    if order.status == Order.Status.PAID:
        return
    if order.status != Order.Status.PENDING:
        log.warning("Order %s in unexpected status %s during apply-paid", order.id, order.status)
        return
    order.status = Order.Status.PAID
    order.save(update_fields=["status", "updated_at"])
    _commit_reservations_for_order(order)
    # Defer until the transaction actually commits so a rollback doesn't
    # fire a spurious invoice-generation task.
    _enqueue_invoice_on_commit(order)


def _apply_order_cancelled(order: Order) -> None:
    """Shared cancel-path for a locked Order. Idempotent.

    Releases reservations and reverts a CHECKING_OUT cart so the customer
    isn't left with a wedged cart after an async failure.
    """
    if order.status == Order.Status.CANCELLED:
        return
    if order.status != Order.Status.PENDING:
        log.warning("Order %s in unexpected status %s during apply-cancel", order.id, order.status)
        return
    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    _release_reservations_for_order(order)
    _revert_cart_if_checking_out(order)


# ---------------------------------------------------------------------------
# Reconciliation sweep -- the "outage = money lost" safety net.
# ---------------------------------------------------------------------------
#
# Two stuck states this task converges:
#
#   A. Payment.status = PENDING, gateway_transaction_id NOT empty
#      A 3DS / async authorize that the customer abandoned. We ask the
#      gateway for the intent's current state and apply it.
#
#   B. Payment.status = PENDING, gateway_transaction_id EMPTY
#      Authorize call never came back (network timeout, worker crash
#      between the gateway response and the DB write). We can't safely
#      retry the charge without the payment-method token (which lives on
#      the Cart, not the Payment), so we mark the payment as FAILED and
#      cancel the order. The matching `Order.idempotency_key` UNIQUE
#      constraint prevents a duplicate retry from creating a second order.
#
# Stale threshold defaults to 10 minutes -- well past any legitimate sync
# authorize latency (single-digit seconds in normal operation) and short
# enough that abandoned 3DS challenges (which have their own gateway-side
# timeout, typically 5 min) get cleaned up promptly.
#
# Runs as `app_admin` via the Celery DB alias (BYPASSRLS), so cross-tenant
# selects work. We use `SELECT FOR UPDATE SKIP LOCKED` to never block on
# rows another reconciler / live checkout is already touching.

RECONCILE_STALE_MINUTES = 10
RECONCILE_BATCH_SIZE = 100
_ADMIN_DB_ALIAS = "admin"  # BYPASSRLS connection -- see apps/iam/views/_base.py


@shared_task(
    base=DurableTask,
    bind=True,
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def reconcile_pending_payments(self, stale_after_minutes: int = RECONCILE_STALE_MINUTES) -> dict:
    """Periodic sweep of Payment rows stuck in PENDING.

    Returns a summary dict for visibility in beat / monitoring:
        {"scanned": N, "converged": M, "cancelled": K, "still_pending": P}
    """
    cutoff = timezone.now() - timedelta(minutes=stale_after_minutes)

    # Snapshot of ids to reconcile, picked outside a long transaction so we
    # don't hold the SELECT FOR UPDATE across per-row gateway calls. Uses
    # the admin alias because the sweep is cross-tenant -- RLS at the
    # app_user connection would filter the result to nothing.
    candidate_ids = list(
        Payment.all_objects.using(_ADMIN_DB_ALIAS)
        .filter(
            status=Payment.Status.PENDING,
            updated_at__lt=cutoff,
        )
        .order_by("updated_at")
        .values_list("id", flat=True)[:RECONCILE_BATCH_SIZE]
    )

    summary = {
        "scanned": len(candidate_ids),
        "converged": 0,
        "cancelled": 0,
        "still_pending": 0,
    }

    for payment_id in candidate_ids:
        try:
            outcome = _reconcile_one(payment_id)
        except Exception:
            log.exception("Reconciliation failed for payment %s", payment_id)
            continue
        summary[outcome] = summary.get(outcome, 0) + 1

    if summary["scanned"]:
        log.info("Payment reconciliation: %s", summary)
    if summary["scanned"] >= RECONCILE_BATCH_SIZE:
        # Full batch means there's likely more behind it. Surface so an
        # operator knows the backlog is growing faster than the beat tick.
        log.warning(
            "Reconcile filled the batch (%s); backlog may be growing",
            RECONCILE_BATCH_SIZE,
        )
    return summary


def _reconcile_one(payment_id) -> str:
    """Process one stuck payment. Returns one of: converged / cancelled / still_pending.

    Sets BOTH the Python tenant context AND the Postgres GUC so the
    tenant-scoped helpers (`_commit_reservations_for_order` etc., shared
    with the webhook path) work against the default DB connection
    regardless of whether the worker is connected as `app_user`
    (RLS-enforced) or `app_admin` (BYPASSRLS).
    """
    # Pre-read to discover the tenant. Routed through the admin alias so
    # the cross-tenant select succeeds without RLS in the way -- the
    # sweep is intrinsically cross-tenant and runs as ops infrastructure.
    pre = (
        Payment.all_objects.using(_ADMIN_DB_ALIAS)
        .filter(id=payment_id, status=Payment.Status.PENDING)
        .values("tenant_id")
        .first()
    )
    if pre is None:
        return "still_pending"

    tenant_id = pre["tenant_id"]
    token = set_current_tenant_id(tenant_id)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET app.current_tenant = %s", [str(tenant_id)])
        try:
            with transaction.atomic():
                # SKIP LOCKED: if another sweep / checkout already holds
                # this row, leave it for next pass instead of waiting.
                payment = (
                    Payment.all_objects.select_for_update(skip_locked=True)
                    .select_related("gateway_config")
                    .filter(id=payment_id, status=Payment.Status.PENDING)
                    .first()
                )
                if payment is None:
                    return "still_pending"

                if payment.gateway_transaction_id:
                    return _reconcile_known_intent(payment)
                return _reconcile_unknown_intent(payment)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET app.current_tenant")
    finally:
        reset_current_tenant_id(token)


def _reconcile_known_intent(payment: Payment) -> str:
    """Case A: ask the gateway for the intent's current state."""
    gateway = registry.get(payment.gateway_config.gateway_name)
    credentials = build_credentials(payment.gateway_config)

    try:
        intent = gateway.retrieve_payment(
            credentials=credentials,
            gateway_transaction_id=payment.gateway_transaction_id,
        )
    except Exception:
        log.exception(
            "Gateway retrieve_payment raised for payment=%s txn=%s",
            payment.id,
            payment.gateway_transaction_id,
        )
        return "still_pending"

    if intent is None or intent.status == GatewayStatus.PENDING:
        # Gateway has no fresh info -- leave it; the next sweep will retry.
        # If it stays PENDING for many sweeps a human should look.
        return "still_pending"

    new_status = map_gateway_status(intent.status)
    payment.status = new_status
    payment.gateway_response = {
        **(payment.gateway_response or {}),
        "reconciled": True,
        "reconciled_intent": intent.raw_response or {},
    }
    payment.save(update_fields=["status", "gateway_response", "updated_at"])

    # Mirror terminal states onto the order.
    if new_status == Payment.Status.CAPTURED:
        _mark_order_paid(payment.order_id)
        return "converged"
    if new_status in (Payment.Status.FAILED, Payment.Status.CANCELLED):
        _mark_order_cancelled_and_release(payment.order_id)
        return "cancelled"
    # AUTHORIZED / REFUNDED -- record the row, leave the order alone.
    return "converged"


def _reconcile_unknown_intent(payment: Payment) -> str:
    """Case B: no gateway_transaction_id, safe path is cancel + release."""
    log.warning(
        "Payment %s has no gateway_transaction_id after %s; cancelling",
        payment.id,
        timezone.now() - payment.updated_at,
    )
    payment.status = Payment.Status.FAILED
    payment.gateway_response = {
        **(payment.gateway_response or {}),
        "reconciled": True,
        "reconcile_reason": "no_gateway_transaction_id",
    }
    payment.save(update_fields=["status", "gateway_response", "updated_at"])
    _mark_order_cancelled_and_release(payment.order_id)
    return "cancelled"


def _mark_order_paid(order_id) -> None:
    order = Order.all_objects.select_for_update().get(id=order_id)
    _apply_order_paid(order)


def _mark_order_cancelled_and_release(order_id) -> None:
    order = Order.all_objects.select_for_update().get(id=order_id)
    _apply_order_cancelled(order)
