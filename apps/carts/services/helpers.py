"""Helpers shared by CartService and external callers (compute_totals)."""

from decimal import Decimal
from uuid import UUID

from django.db.models import F

from apps.carts.models import Cart
from apps.carts.services.cart_totals import CartTotals
from apps.core.exceptions import CartNotFound


def _lock_active_cart(*, customer_id: UUID) -> Cart:
    try:
        return Cart.objects.select_for_update().get(
            customer_id=customer_id, status=Cart.Status.ACTIVE
        )
    except Cart.DoesNotExist as e:
        raise CartNotFound("No active cart for this customer") from e


def _bump_and_return(cart: Cart) -> Cart:
    """Increment version and re-fetch with all related fields. Final step
    of every mutation."""
    Cart.objects.filter(id=cart.id).update(version=F("version") + 1)
    cart.refresh_from_db()
    # Reload with select_related/prefetch for serialization
    cart = (
        Cart.objects.select_related(
            "shipping_address", "billing_address", "selected_payment_method"
        )
        .prefetch_related("items__product", "applied_coupons__coupon")
        .get(id=cart.id)
    )
    cart._totals = compute_totals(cart)
    return cart


def _compute_subtotal(cart: Cart) -> Decimal:
    return sum(
        (item.unit_price_snapshot * item.quantity for item in cart.items.all()),
        Decimal("0"),
    )


def compute_totals(cart: Cart) -> CartTotals:
    subtotal = _compute_subtotal(cart)
    discount = Decimal("0")
    for applied in cart.applied_coupons.all():
        discount += applied.coupon.compute_discount(subtotal)
    discount = min(discount, subtotal)
    return CartTotals(
        subtotal=subtotal.quantize(Decimal("0.01")),
        discount_total=discount.quantize(Decimal("0.01")),
        grand_total=(subtotal - discount).quantize(Decimal("0.01")),
        currency=cart.currency or "",
    )
