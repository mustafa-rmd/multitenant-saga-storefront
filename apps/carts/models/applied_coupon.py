from django.db import models

from apps.carts.models.cart import Cart
from apps.core.models import TenantScopedModel


class AppliedCoupon(TenantScopedModel):
    """Links a Coupon to a Cart. Discount is recomputed on read; we store
    no denormalized amount here because subtotal can change as items
    are added/removed."""

    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="applied_coupons")
    coupon = models.ForeignKey("coupons.Coupon", on_delete=models.PROTECT, related_name="+")
    applied_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "carts_appliedcoupon"
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "coupon"],
                name="uniq_coupon_per_cart",
            ),
        ]
