from rest_framework import serializers

from apps.carts.models import CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            "id",
            "product_id",
            "product_name",
            "product_sku",
            "quantity",
            "unit_price_snapshot",
            "currency",
            "line_total",
        ]
        read_only_fields = fields

    def get_line_total(self, obj) -> str:
        return str(obj.unit_price_snapshot * obj.quantity)
