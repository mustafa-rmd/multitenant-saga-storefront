from decimal import Decimal

from django.db import models
from django.utils import timezone

from apps.core.models import TenantScopedModel
from apps.coupons.models.customer_type_restriction import CustomerTypeRestriction
from apps.coupons.models.discount_type import DiscountType


class Coupon(TenantScopedModel):
    code = models.CharField(max_length=64)
    discount_type = models.CharField(max_length=16, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, blank=True, default="")  # required for fixed
    # --- Constraints ---
    min_cart_subtotal = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    allowed_countries = models.JSONField(default=list, blank=True)
    customer_type_restriction = models.CharField(
        max_length=4,
        choices=CustomerTypeRestriction.choices,
        default=CustomerTypeRestriction.ANY,
    )
    max_uses = models.IntegerField(null=True, blank=True)
    uses_count = models.IntegerField(default=0)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "coupons_coupon"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                name="uniq_coupon_code_per_tenant",
            ),
        ]

    def __str__(self):
        return self.code

    # --- Constraint checks (raise domain errors on failure) ---

    def validate(
        self,
        *,
        cart_subtotal: Decimal,
        cart_currency: str,
        shipping_country: str | None = None,
        customer_type: str | None = None,
    ) -> None:
        """Raise the appropriate DomainError if any constraint fails."""
        from apps.core.exceptions import (
            CouponCountryRestricted,
            CouponExhausted,
            CouponExpired,
            CouponInvalid,
            CouponMinNotMet,
        )

        if not self.is_active:
            raise CouponInvalid("Coupon is not active")

        now = timezone.now()
        if self.valid_from and now < self.valid_from:
            raise CouponInvalid("Coupon is not yet valid")
        if self.valid_until and now > self.valid_until:
            raise CouponExpired(f"Coupon expired on {self.valid_until.date()}")

        if self.max_uses is not None and self.uses_count >= self.max_uses:
            raise CouponExhausted("This coupon has reached its usage limit")

        if self.discount_type == DiscountType.FIXED and self.currency != cart_currency:
            raise CouponInvalid(
                f"Coupon currency {self.currency} does not match cart currency {cart_currency}"
            )

        if self.min_cart_subtotal is not None and cart_subtotal < self.min_cart_subtotal:
            raise CouponMinNotMet(
                required=self.min_cart_subtotal,
                current=cart_subtotal,
            )

        if self.allowed_countries and (
            not shipping_country
            or shipping_country.upper() not in [c.upper() for c in self.allowed_countries]
        ):
            raise CouponCountryRestricted("This coupon is not valid for the shipping country")

        if (
            self.customer_type_restriction != CustomerTypeRestriction.ANY
            and customer_type != self.customer_type_restriction
        ):
            raise CouponInvalid(
                f"This coupon requires customer type {self.customer_type_restriction}"
            )

    def compute_discount(self, subtotal: Decimal) -> Decimal:
        """Compute the discount amount for a given subtotal. Never returns
        more than the subtotal."""
        if self.discount_type == DiscountType.PERCENTAGE:
            raw = subtotal * self.discount_value / Decimal("100")
        else:
            raw = self.discount_value
        return min(raw, subtotal).quantize(Decimal("0.01"))
