"""
CheckoutService -- the saga that converts a cart to an order.

Seven phases, each committing in its own transaction so a crash leaves
recoverable state:

    1. Lock cart  -- SELECT FOR UPDATE, validate state, transition to checking_out
    2. Validate   -- preconditions (items, addresses, payment method, coupons)
    3. Reserve    -- create InventoryReservation rows with TTL (deterministic lock order)
    4. Order      -- create Order + OrderItems
    5. Authorize  -- call gateway, persist Payment
    6. Commit     -- transition cart to converted, back-link order
    7. Capture    -- sync gateways: capture now; async: wait for webhook

Compensating actions run for earlier phases on failure of a later one.
"""

import logging
from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.carts.models import Cart
from apps.core.exceptions import OrderNotCancellable, PaymentFailed, ResourceNotFound
from apps.orders.models import InventoryReservation, Order, ReservationStatus
from apps.orders.services.checkout_helpers import (
    _cancel_order,
    _commit_reservations,
    _create_order,
    _enqueue_post_payment_tasks,
    _find_existing_checkout,
    _lock_and_validate_cart,
    _release_reservations,
    _reserve_stock,
    _reverse_committed_reservations,
    _revert_cart_to_active,
    _validate_preconditions,
)
from apps.orders.services.checkout_result import CheckoutResult
from apps.payments.models import Payment, PaymentMethodType
from apps.payments.services import PaymentService

# Net-30 / net-60 etc. translate to a payment_due_date snapshot at checkout.
_PO_TERMS_TO_DAYS = {
    "net_15": 15,
    "net_30": 30,
    "net_60": 60,
    "net_90": 90,
}

log = logging.getLogger(__name__)


class CheckoutService:
    @staticmethod
    def checkout(
        *,
        customer_id: UUID,
        idempotency_key: str,
        expected_version: int | None = None,
        payment_metadata: dict | None = None,
    ) -> CheckoutResult:
        # Idempotency short-circuit
        existing = _find_existing_checkout(idempotency_key)
        if existing:
            log.info("Idempotent checkout replay: %s", idempotency_key)
            return existing

        # --- Phase 1: Lock and validate cart ---
        with transaction.atomic():
            cart = _lock_and_validate_cart(
                customer_id=customer_id,
                expected_version=expected_version,
            )
            cart.status = Cart.Status.CHECKING_OUT
            cart.save(update_fields=["status", "updated_at"])

        # --- Phase 2: Validate preconditions ---
        # Coupons re-validated under reservation lock in phase 3
        try:
            _validate_preconditions(cart)
        except Exception:
            _revert_cart_to_active(cart.id)
            raise

        # --- Phase 3: Reserve stock ---
        try:
            reservations = _reserve_stock(cart)
        except Exception:
            _revert_cart_to_active(cart.id)
            raise

        # --- Phase 4: Create order (also increments coupon uses_count) ---
        try:
            order = _create_order(cart, idempotency_key=idempotency_key)
        except Exception:
            _release_reservations(reservations)
            _revert_cart_to_active(cart.id)
            raise

        # --- Phase 5: Authorize payment (or record PO if invoiced) ---
        payment_method = cart.selected_payment_method
        is_purchase_order = payment_method.method_type == PaymentMethodType.PURCHASE_ORDER

        if is_purchase_order:
            # PO path: no gateway call. Snapshot terms + due-date onto the
            # order, commit reservations (ship-first model), fire invoice,
            # and exit. Tenant admin flips the order to PAID later via
            # POST /admin/orders/{id}/mark-paid once the invoice clears.
            try:
                payment = PaymentService.create_invoice_pending_payment(
                    order_id=order.id,
                    amount=order.grand_total,
                    currency=order.currency,
                    idempotency_key=f"{idempotency_key}:po",
                )
            except Exception:
                _cancel_order(order)
                _release_reservations(reservations)
                _revert_cart_to_active(cart.id)
                raise

            terms = payment_method.payment_terms or "net_30"
            due_days = _PO_TERMS_TO_DAYS.get(terms, 30)
            with transaction.atomic():
                order.refresh_from_db()
                order.payment_terms = terms
                order.payment_due_date = (timezone.now() + timedelta(days=due_days)).date()
                order.cart_id = cart.id
                order.save(
                    update_fields=[
                        "payment_terms",
                        "payment_due_date",
                        "cart",
                        "updated_at",
                    ]
                )
                cart.refresh_from_db()
                cart.status = Cart.Status.CONVERTED
                cart.save(update_fields=["status", "updated_at"])
                for r in reservations:
                    r.order = order
                    r.save(update_fields=["order", "updated_at"])
                _commit_reservations(reservations)
            _enqueue_post_payment_tasks(order)
            return CheckoutResult(order=order, payment_status="invoice_pending")

        # Enrich the payment metadata with order + customer identity so
        # gateway dashboards (Stripe, HyperPay, etc.) show a meaningful
        # row instead of a bare amount. The adapter picks what it needs
        # (Stripe maps `customer_email` → receipt_email, builds a
        # `description` from order_number + customer name).
        customer = cart.customer
        enriched_metadata = {
            "order_id": str(order.id),
            "order_number": str(order.order_number),
            "customer_id": str(customer.id),
            "customer_email": customer.email,
            "customer_name": customer.name or "",
            "is_b2b": "true" if customer.is_b2b else "false",
        }
        if customer.is_b2b and customer.company_name:
            enriched_metadata["company_name"] = customer.company_name
        if payment_metadata:
            enriched_metadata.update(payment_metadata)

        try:
            payment = PaymentService.authorize_payment(
                order_id=order.id,
                payment_method_id=cart.selected_payment_method_id,
                amount=order.grand_total,
                currency=order.currency,
                idempotency_key=f"{idempotency_key}:auth",
                metadata=enriched_metadata,
            )
        except PaymentFailed:
            _cancel_order(order)
            _release_reservations(reservations)
            _revert_cart_to_active(cart.id)
            raise

        # --- Phase 6: Commit cart ---
        with transaction.atomic():
            cart.refresh_from_db()
            cart.status = Cart.Status.CONVERTED
            cart.save(update_fields=["status", "updated_at"])
            order.cart_id = cart.id
            order.save(update_fields=["cart", "updated_at"])
            for r in reservations:
                r.order = order
                r.save(update_fields=["order", "updated_at"])

        # --- Phase 7: Capture (sync) or wait (async / 3DS) ---
        if payment.status == Payment.Status.AUTHORIZED:
            try:
                payment = PaymentService.capture_payment(payment_id=payment.id)
                with transaction.atomic():
                    order.refresh_from_db()
                    order.status = Order.Status.PAID
                    order.save(update_fields=["status", "updated_at"])
                    _commit_reservations(reservations)
                _enqueue_post_payment_tasks(order)
                return CheckoutResult(
                    order=order,
                    payment_status="captured",
                )
            except Exception:
                log.exception("Capture failed; order left in PENDING for reconciliation")
                return CheckoutResult(
                    order=order,
                    payment_status="capture_pending",
                )

        if payment.status == Payment.Status.PENDING:
            # 3DS / async -- webhook will move forward
            next_action = (payment.gateway_response or {}).get("next_action")
            return CheckoutResult(
                order=order,
                payment_status="pending",
                next_action=next_action,
            )

        # Shouldn't reach here; PaymentFailed should have raised earlier
        raise PaymentFailed(detail=f"Unexpected payment status: {payment.status}")

    @staticmethod
    @transaction.atomic
    def cancel_order(*, customer_id: UUID, order_id: UUID) -> Order:
        """Cancel a `pending` order, releasing inventory + voiding payment.

        Only orders in `pending` status are cancellable — once a payment
        is captured the path is refund, not cancel. Idempotent: cancelling
        an already-cancelled order is a no-op and returns the order as-is.

        Two reservation states to unwind:
          * `active` — card path: stock is still in `reserved_quantity`,
            release it via `_release_reservations`.
          * `committed` — PO path: stock was already deducted from
            `stock_quantity` at checkout (ship-first model), so we
            restore it via `_reverse_committed_reservations`.

        Steps:
          1. Lock the order row + verify ownership (customer scope).
          2. Reject if status is anything but `pending` or `cancelled`.
          3. Release / reverse InventoryReservation rows per their state.
          4. Mark any open Payments (`authorized`, `pending`, or
             `invoice_pending`) as `cancelled`. We don't call the
             gateway's void API in this POC — reconciliation would
             sweep hanging auths in production.
          5. Transition order to `cancelled`.
        """
        try:
            order = (
                Order.objects.select_for_update().filter(customer_id=customer_id).get(id=order_id)
            )
        except Order.DoesNotExist as e:
            raise ResourceNotFound("Order not found") from e

        if order.status == Order.Status.CANCELLED:
            return order  # idempotent

        if order.status != Order.Status.PENDING:
            raise OrderNotCancellable(
                detail=f"Cannot cancel order in status '{order.status}'",
                meta={"order_id": str(order.id), "status": order.status},
            )

        active_reservations = list(
            InventoryReservation.objects.select_for_update().filter(
                order_id=order.id, status=ReservationStatus.ACTIVE
            )
        )
        if active_reservations:
            _release_reservations(active_reservations)

        committed_reservations = list(
            InventoryReservation.objects.select_for_update().filter(
                order_id=order.id, status=ReservationStatus.COMMITTED
            )
        )
        if committed_reservations:
            _reverse_committed_reservations(committed_reservations)

        Payment.objects.filter(
            order_id=order.id,
            status__in=(
                Payment.Status.AUTHORIZED,
                Payment.Status.PENDING,
                Payment.Status.INVOICE_PENDING,
            ),
        ).update(status=Payment.Status.CANCELLED)

        order.status = Order.Status.CANCELLED
        order.save(update_fields=["status", "updated_at"])
        return order
