"""Helpers used by CheckoutService.checkout to keep each saga phase
in a focused, transactional unit."""

import logging
from datetime import timedelta
from uuid import UUID

from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone

from apps.carts.models import Cart
from apps.carts.services import compute_totals
from apps.catalog.models import Product
from apps.core.exceptions import (
    CartNotCheckoutReady,
    CartNotFound,
    CartVersionConflict,
    CouponExhausted,
    InsufficientStock,
)
from apps.coupons.models import Coupon
from apps.orders.models import (
    InventoryReservation,
    Order,
    OrderItem,
    ReservationStatus,
)
from apps.orders.services.checkout_result import CheckoutResult

log = logging.getLogger(__name__)


def _find_existing_checkout(idempotency_key: str) -> CheckoutResult | None:
    try:
        order = Order.objects.get(idempotency_key=idempotency_key)
    except Order.DoesNotExist:
        return None
    payment = order.payments.order_by("-created_at").first()
    if not payment:
        return CheckoutResult(order=order, payment_status="pending")
    payment_status = payment.status
    next_action = (payment.gateway_response or {}).get("next_action")
    return CheckoutResult(
        order=order,
        payment_status=payment_status,
        next_action=next_action,
    )


def _lock_and_validate_cart(*, customer_id, expected_version):
    # `of=("self",)` locks only the Cart row, not the joined rows. Required
    # because select_related on nullable FKs (shipping_address, billing_address,
    # selected_payment_method) produces LEFT OUTER JOINs, and Postgres rejects
    # FOR UPDATE on the nullable side of an outer join.
    try:
        cart = (
            Cart.objects.select_for_update(of=("self",))
            .select_related(
                "shipping_address", "billing_address", "selected_payment_method", "customer"
            )
            .prefetch_related("items__product", "applied_coupons__coupon")
            .get(customer_id=customer_id, status=Cart.Status.ACTIVE)
        )
    except Cart.DoesNotExist as e:
        raise CartNotFound("No active cart for this customer") from e

    if expected_version is not None and cart.version != expected_version:
        raise CartVersionConflict(expected=expected_version, actual=cart.version)

    return cart


def _validate_preconditions(cart: Cart) -> None:
    if not cart.items.exists():
        raise CartNotCheckoutReady("Cart is empty")
    if not cart.shipping_address_id:
        raise CartNotCheckoutReady("Shipping address required")
    if not cart.billing_address_id:
        raise CartNotCheckoutReady("Billing address required")
    if not cart.selected_payment_method_id:
        raise CartNotCheckoutReady("Payment method required")

    # Re-validate coupons against current cart totals
    totals = compute_totals(cart)
    shipping_country = cart.shipping_address.country if cart.shipping_address_id else None
    for applied in cart.applied_coupons.all():
        applied.coupon.validate(
            cart_subtotal=totals.subtotal,
            cart_currency=cart.currency,
            shipping_country=shipping_country,
            customer_type=cart.customer.customer_type,
        )


def _reserve_stock(cart: Cart) -> list[InventoryReservation]:
    item_qtys = {item.product_id: item.quantity for item in cart.items.all()}
    # Deterministic lock order to prevent deadlocks
    product_ids_sorted = sorted(item_qtys.keys(), key=lambda x: str(x))

    expires_at = timezone.now() + timedelta(minutes=15)
    reservations = []

    with transaction.atomic():
        products = list(
            Product.objects.select_for_update().filter(id__in=product_ids_sorted).order_by("id")
        )

        insufficient = []
        for product in products:
            requested = item_qtys[product.id]
            available = product.stock_quantity - product.reserved_quantity
            if available < requested:
                insufficient.append((product.id, available, requested))

        if insufficient:
            raise InsufficientStock(items=insufficient)

        for product in products:
            qty = item_qtys[product.id]
            res = InventoryReservation.objects.create(
                cart=cart,
                product=product,
                quantity=qty,
                expires_at=expires_at,
                status=ReservationStatus.ACTIVE,
            )
            Product.objects.filter(id=product.id).update(
                reserved_quantity=F("reserved_quantity") + qty
            )
            reservations.append(res)

    return reservations


def _create_order(cart: Cart, *, idempotency_key: str) -> Order:
    totals = compute_totals(cart)

    with transaction.atomic():
        # Increment coupon uses (under coupon row lock)
        for applied in cart.applied_coupons.select_related("coupon").all():
            # Lock the coupon row to atomically check + bump uses_count
            locked = Coupon.objects.select_for_update().get(id=applied.coupon_id)
            if locked.max_uses is not None and locked.uses_count >= locked.max_uses:
                raise CouponExhausted(
                    f"Coupon {locked.code} reached its usage limit during checkout"
                )
            Coupon.objects.filter(id=locked.id).update(uses_count=F("uses_count") + 1)

        order_number = _next_order_number(cart.tenant_id)
        order = Order.objects.create(
            customer=cart.customer,
            order_number=order_number,
            status=Order.Status.PENDING,
            subtotal=totals.subtotal,
            discount_total=totals.discount_total,
            grand_total=totals.grand_total,
            currency=cart.currency,
            shipping_address=cart.shipping_address.to_snapshot(),
            billing_address=cart.billing_address.to_snapshot(),
            is_b2b=cart.customer.is_b2b,
            tax_id=cart.customer.tax_id if cart.customer.is_b2b else "",
            idempotency_key=idempotency_key,
        )

        OrderItem.objects.bulk_create(
            [
                OrderItem(
                    order=order,
                    product=item.product,
                    product_sku_snapshot=item.product.sku,
                    product_name_snapshot=item.product.name,
                    quantity=item.quantity,
                    unit_price=item.unit_price_snapshot,
                    line_total=item.unit_price_snapshot * item.quantity,
                    currency=item.currency,
                    tenant_id=cart.tenant_id,
                )
                for item in cart.items.all()
            ]
        )

    return order


def _next_order_number(tenant_id: UUID) -> int:
    """Per-tenant monotonic order number from a Postgres sequence.

    The sequence must be pre-created — the platform-admin tenant-create
    endpoint provisions both order/invoice sequences in the same
    transaction. Live request paths run as app_user, which lacks CREATE
    on schema public, so DDL here would fail -- even CREATE SEQUENCE IF
    NOT EXISTS, because Postgres checks the CREATE privilege before the
    existence check.
    """
    safe_id = str(tenant_id).replace("-", "_")
    seq_name = f"order_number_seq_{safe_id}"
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT nextval('{seq_name}');")
        return cursor.fetchone()[0]


def _revert_cart_to_active(cart_id: UUID) -> None:
    Cart.objects.filter(id=cart_id, status=Cart.Status.CHECKING_OUT).update(
        status=Cart.Status.ACTIVE,
    )


def _release_reservations(reservations: list[InventoryReservation]) -> None:
    with transaction.atomic():
        for res in reservations:
            res.refresh_from_db()
            if res.status != ReservationStatus.ACTIVE:
                continue
            Product.objects.filter(id=res.product_id).update(
                reserved_quantity=F("reserved_quantity") - res.quantity
            )
            res.status = ReservationStatus.RELEASED
            res.save(update_fields=["status", "updated_at"])


def _commit_reservations(reservations: list[InventoryReservation]) -> None:
    """Commit reservations: deduct stock for real, mark as committed."""
    with transaction.atomic():
        for res in reservations:
            res.refresh_from_db()
            if res.status != ReservationStatus.ACTIVE:
                continue
            Product.objects.filter(id=res.product_id).update(
                stock_quantity=F("stock_quantity") - res.quantity,
                reserved_quantity=F("reserved_quantity") - res.quantity,
            )
            res.status = ReservationStatus.COMMITTED
            res.save(update_fields=["status", "updated_at"])


def _reverse_committed_reservations(reservations: list[InventoryReservation]) -> None:
    """Undo a previously committed reservation: stock_quantity goes back up.

    Used by the cancel-order path for PO orders (whose stock was committed
    at checkout under the ship-first model). For card orders this never
    fires because card-path reservations stay `active` until capture.
    """
    with transaction.atomic():
        for res in reservations:
            res.refresh_from_db()
            if res.status != ReservationStatus.COMMITTED:
                continue
            Product.objects.filter(id=res.product_id).update(
                stock_quantity=F("stock_quantity") + res.quantity,
            )
            res.status = ReservationStatus.RELEASED
            res.save(update_fields=["status", "updated_at"])


def _cancel_order(order: Order) -> None:
    with transaction.atomic():
        order.refresh_from_db()
        if order.status in (Order.Status.PENDING, Order.Status.PAID):
            order.status = Order.Status.CANCELLED
            order.save(update_fields=["status", "updated_at"])


def _enqueue_post_payment_tasks(order: Order) -> None:
    """Fire-and-forget Celery tasks. Failures here don't roll back the order."""
    from apps.orders.tasks import generate_invoice

    try:
        generate_invoice.delay(str(order.tenant_id), str(order.id))
    except Exception:
        log.exception("Failed to enqueue post-payment tasks for order %s", order.id)
