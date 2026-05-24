from decimal import Decimal

from rest_framework import serializers

from apps.carts.models import AppliedCoupon


class AppliedCouponSerializer(serializers.ModelSerializer):
    code = serializers.CharField(source="coupon.code", read_only=True)
    discount_amount = serializers.SerializerMethodField()

    class Meta:
        model = AppliedCoupon
        fields = ["code", "discount_amount", "applied_at"]
        read_only_fields = fields

    def get_discount_amount(self, obj) -> str:
        # Recompute from cart subtotal (this serializer is always used in
        # context of a cart with _totals attached, but be defensive)
        cart = obj.cart
        subtotal = sum(
            (i.unit_price_snapshot * i.quantity for i in cart.items.all()),
            Decimal("0"),
        )
        return str(obj.coupon.compute_discount(subtotal))
