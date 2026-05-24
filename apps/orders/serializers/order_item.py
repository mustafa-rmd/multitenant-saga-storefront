from rest_framework import serializers

from apps.orders.models import OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product_id",
            "product_sku_snapshot",
            "product_name_snapshot",
            "quantity",
            "unit_price",
            "line_total",
            "currency",
        ]
        read_only_fields = fields
