"""All mutations return the full cart with totals computed and attached
as `cart._totals`. The serializer reads from there.

Every method operates on the customer's single active cart. The cart is
identified solely by customer_id (+ status=ACTIVE) -- there is no cart_id
parameter because the database enforces one active cart per customer."""

from uuid import UUID

from django.db import transaction
from django.db.models import F

from apps.carts.models import AppliedCoupon, Cart, CartItem
from apps.carts.services.helpers import (
    _bump_and_return,
    _compute_subtotal,
    _lock_active_cart,
    compute_totals,
)
from apps.catalog.models import Product
from apps.core.exceptions import (
    AddressNotFound,
    CartNotFound,
    CouponAlreadyApplied,
    CouponNotFound,
    CurrencyMismatch,
    InsufficientStock,
    PaymentMethodNotFound,
    ProductNotFound,
)
from apps.coupons.models import Coupon


class CartService:
    # ============================================================
    # Items
    # ============================================================

    @staticmethod
    @transaction.atomic
    def add_item(
        *,
        customer_id: UUID,
        product_id: UUID,
        quantity: int,
    ) -> Cart:
        # Lazy-create the active cart for this customer
        cart, _ = Cart.objects.select_for_update().get_or_create(
            customer_id=customer_id,
            status=Cart.Status.ACTIVE,
        )

        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist as e:
            raise ProductNotFound(product_id=product_id) from e

        # Currency lock-in on first item. Persist immediately -- _bump_and_return
        # ends with refresh_from_db() which would otherwise wipe the in-memory value.
        if not cart.currency:
            cart.currency = product.currency
            cart.save(update_fields=["currency", "updated_at"])
        elif cart.currency != product.currency:
            raise CurrencyMismatch(
                cart_currency=cart.currency,
                product_currency=product.currency,
            )

        existing_item = cart.items.filter(product_id=product_id).first()
        existing_qty = existing_item.quantity if existing_item else 0
        new_total = existing_qty + quantity

        if new_total > product.available_quantity:
            raise InsufficientStock(
                product_id=product_id,
                available=product.available_quantity,
                requested=new_total,
            )

        if existing_item:
            CartItem.objects.filter(id=existing_item.id).update(quantity=F("quantity") + quantity)
        else:
            CartItem.objects.create(
                cart=cart,
                product=product,
                quantity=quantity,
                unit_price_snapshot=product.price,
                currency=product.currency,
            )

        return _bump_and_return(cart)

    @staticmethod
    @transaction.atomic
    def remove_item(
        *,
        customer_id: UUID,
        item_id: UUID,
    ) -> Cart:
        cart = _lock_active_cart(customer_id=customer_id)
        deleted, _ = cart.items.filter(id=item_id).delete()
        if not deleted:
            raise CartNotFound("Cart item not found")

        # If cart now empty, clear currency so a different-currency product
        # can be added next. Persist before _bump_and_return's refresh_from_db.
        if not cart.items.exists():
            cart.currency = ""
            cart.save(update_fields=["currency", "updated_at"])

        return _bump_and_return(cart)

    @staticmethod
    @transaction.atomic
    def update_item_quantity(
        *,
        customer_id: UUID,
        item_id: UUID,
        quantity: int,
    ) -> Cart:
        """Replace the line's quantity (does not add to it).

        For incrementing, callers should use POST /cart/items which merges
        on existing lines. PATCH is for direct quantity adjustment from a
        cart-edit UI. Quantity 0 is rejected by the serializer — use
        DELETE for that.
        """
        cart = _lock_active_cart(customer_id=customer_id)
        try:
            item = cart.items.select_related("product").get(id=item_id)
        except CartItem.DoesNotExist as e:
            raise CartNotFound("Cart item not found") from e

        if quantity > item.product.available_quantity:
            raise InsufficientStock(
                product_id=item.product_id,
                available=item.product.available_quantity,
                requested=quantity,
            )

        CartItem.objects.filter(id=item.id).update(quantity=quantity)
        return _bump_and_return(cart)

    @staticmethod
    @transaction.atomic
    def clear_cart(*, customer_id: UUID) -> None:
        """Abandon the active cart: drop all items + coupons + slot
        references, mark status=ABANDONED, do NOT bump version (the cart
        is dead from the client's perspective).

        Idempotent — calling on a customer with no active cart is a
        no-op (caller can treat this as success). The next POST
        /cart/items will lazy-create a fresh ACTIVE cart, so this is
        non-destructive from the user's perspective: they just lose
        their pending selections.
        """
        cart = (
            Cart.objects.select_for_update()
            .filter(customer_id=customer_id, status=Cart.Status.ACTIVE)
            .first()
        )
        if cart is None:
            return

        cart.items.all().delete()
        cart.applied_coupons.all().delete()
        cart.shipping_address = None
        cart.billing_address = None
        cart.selected_payment_method = None
        cart.currency = ""
        cart.status = Cart.Status.ABANDONED
        cart.save(
            update_fields=[
                "shipping_address",
                "billing_address",
                "selected_payment_method",
                "currency",
                "status",
                "updated_at",
            ]
        )

    # ============================================================
    # Coupons
    # ============================================================

    @staticmethod
    @transaction.atomic
    def apply_coupon(
        *,
        customer_id: UUID,
        code: str,
    ) -> Cart:
        cart = _lock_active_cart(customer_id=customer_id)

        try:
            coupon = Coupon.objects.get(code=code)
        except Coupon.DoesNotExist as e:
            raise CouponNotFound("Invalid coupon code") from e

        # Validate. This raises specific domain exceptions; bubble them up.
        subtotal = _compute_subtotal(cart)
        shipping_country = cart.shipping_address.country if cart.shipping_address_id else None
        coupon.validate(
            cart_subtotal=subtotal,
            cart_currency=cart.currency or "",
            shipping_country=shipping_country,
            customer_type=cart.customer.customer_type,
        )

        if cart.applied_coupons.filter(coupon=coupon).exists():
            raise CouponAlreadyApplied(f"Coupon {code} is already applied to this cart")

        AppliedCoupon.objects.create(cart=cart, coupon=coupon)
        return _bump_and_return(cart)

    @staticmethod
    @transaction.atomic
    def remove_coupon(
        *,
        customer_id: UUID,
        code: str,
    ) -> Cart:
        """Idempotent. 404 only when `code` is unknown on this tenant.

        If the coupon exists on the tenant but was never applied (or has
        already been removed), the call returns the cart unchanged with no
        version bump — matching DELETE's REST contract.
        """
        cart = _lock_active_cart(customer_id=customer_id)

        if not Coupon.objects.filter(code=code).exists():
            raise CouponNotFound(f"Coupon {code} not found")

        deleted, _ = cart.applied_coupons.filter(coupon__code=code).delete()
        if not deleted:
            return CartService.get_cart(customer_id=customer_id)

        return _bump_and_return(cart)

    @staticmethod
    def preview_coupon(*, customer_id: UUID, code: str) -> dict:
        """Validate a coupon against the customer's active cart without
        persisting anything.

        Runs the same `Coupon.validate()` pipeline the apply path uses, so
        the failure surface is identical (caller sees `coupon_min_not_met`,
        `coupon_expired`, etc.). On success returns the discount that
        *would* be applied and the resulting subtotal so the UI can show
        "you save N" without committing.

        Read-only: no `SELECT FOR UPDATE`, no cart version bump.
        """
        from decimal import Decimal

        from apps.carts.services.helpers import _compute_subtotal, compute_totals

        cart = CartService.get_cart(customer_id=customer_id)

        try:
            coupon = Coupon.objects.get(code=code)
        except Coupon.DoesNotExist as e:
            raise CouponNotFound("Invalid coupon code") from e

        subtotal = _compute_subtotal(cart)
        shipping_country = cart.shipping_address.country if cart.shipping_address_id else None
        # Raises on failure -- bubbles up through the standard error envelope
        coupon.validate(
            cart_subtotal=subtotal,
            cart_currency=cart.currency or "",
            shipping_country=shipping_country,
            customer_type=cart.customer.customer_type,
        )

        # Coupon is already applied? Surface that as a non-fatal hint so the
        # UI can disable the "Apply" button rather than rendering "valid".
        already_applied = cart.applied_coupons.filter(coupon=coupon).exists()

        # What totals would look like AFTER applying this coupon on top of
        # anything already applied. Cap-at-subtotal logic lives in
        # compute_totals; we replicate just the marginal-discount math here.
        current_totals = compute_totals(cart)
        marginal_discount = coupon.compute_discount(subtotal)
        if already_applied:
            marginal_discount = Decimal("0.00")
        projected_discount = min(current_totals.discount_total + marginal_discount, subtotal)
        projected_grand_total = (subtotal - projected_discount).quantize(Decimal("0.01"))

        return {
            "valid": True,
            "code": coupon.code,
            "already_applied": already_applied,
            "discount": str(marginal_discount.quantize(Decimal("0.01"))),
            "projected_discount_total": str(projected_discount),
            "projected_grand_total": str(projected_grand_total),
            "currency": cart.currency or "",
        }

    # ============================================================
    # Address / payment slots
    # ============================================================

    @staticmethod
    @transaction.atomic
    def set_shipping_address(
        *,
        customer_id: UUID,
        address_id: UUID,
    ) -> Cart:
        from apps.customers.models import Address

        cart = _lock_active_cart(customer_id=customer_id)
        try:
            address = Address.objects.get(id=address_id, customer_id=customer_id)
        except Address.DoesNotExist as e:
            raise AddressNotFound(f"Address {address_id} not found") from e
        cart.shipping_address = address
        cart.save(update_fields=["shipping_address", "updated_at"])
        return _bump_and_return(cart)

    @staticmethod
    @transaction.atomic
    def set_billing_address(
        *,
        customer_id: UUID,
        address_id: UUID,
    ) -> Cart:
        from apps.customers.models import Address

        cart = _lock_active_cart(customer_id=customer_id)
        try:
            address = Address.objects.get(id=address_id, customer_id=customer_id)
        except Address.DoesNotExist as e:
            raise AddressNotFound(f"Address {address_id} not found") from e
        cart.billing_address = address
        cart.save(update_fields=["billing_address", "updated_at"])
        return _bump_and_return(cart)

    @staticmethod
    @transaction.atomic
    def set_payment_method(
        *,
        customer_id: UUID,
        payment_method_id: UUID,
    ) -> Cart:
        from apps.payments.models import PaymentMethod

        cart = _lock_active_cart(customer_id=customer_id)
        try:
            pm = PaymentMethod.objects.get(id=payment_method_id, customer_id=customer_id)
        except PaymentMethod.DoesNotExist as e:
            raise PaymentMethodNotFound(f"Payment method {payment_method_id} not found") from e
        cart.selected_payment_method = pm
        cart.save(update_fields=["selected_payment_method", "updated_at"])
        return _bump_and_return(cart)

    # ============================================================
    # Read
    # ============================================================

    @staticmethod
    def get_cart(*, customer_id: UUID) -> Cart:
        try:
            cart = (
                Cart.objects.select_related(
                    "shipping_address", "billing_address", "selected_payment_method", "customer"
                )
                .prefetch_related("items__product", "applied_coupons__coupon")
                .get(customer_id=customer_id, status=Cart.Status.ACTIVE)
            )
        except Cart.DoesNotExist as e:
            raise CartNotFound("No active cart for this customer") from e
        cart._totals = compute_totals(cart)
        return cart
