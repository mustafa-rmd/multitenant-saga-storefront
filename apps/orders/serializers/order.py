from rest_framework import serializers

from apps.orders.models import Order
from apps.orders.serializers.order_item import OrderItemSerializer


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "subtotal",
            "discount_total",
            "grand_total",
            "currency",
            "shipping_address",
            "billing_address",
            "is_b2b",
            "tax_id",
            "payment_terms",
            "po_number",
            "payment_due_date",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
