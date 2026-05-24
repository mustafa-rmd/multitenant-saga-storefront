from rest_framework import serializers

from apps.carts.models import Cart
from apps.carts.serializers.applied_coupon import AppliedCouponSerializer
from apps.carts.serializers.cart_item import CartItemSerializer


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    applied_coupons = AppliedCouponSerializer(many=True, read_only=True)
    totals = serializers.SerializerMethodField()
    shipping_address_id = serializers.UUIDField(read_only=True, allow_null=True)
    billing_address_id = serializers.UUIDField(read_only=True, allow_null=True)
    selected_payment_method_id = serializers.UUIDField(read_only=True, allow_null=True)
    customer_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Cart
        fields = [
            "id",
            "customer_id",
            "status",
            "currency",
            "version",
            "items",
            "applied_coupons",
            "shipping_address_id",
            "billing_address_id",
            "selected_payment_method_id",
            "totals",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_totals(self, obj) -> dict:
        totals = getattr(obj, "_totals", None)
        if totals is None:
            from apps.carts.services import compute_totals

            totals = compute_totals(obj)
        return {
            "subtotal": str(totals.subtotal),
            "discount_total": str(totals.discount_total),
            "grand_total": str(totals.grand_total),
            "currency": totals.currency,
        }
