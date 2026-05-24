from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Add 2 widgets",
            value={
                "product_id": "00000000-0000-0000-0000-000000000000",
                "quantity": 2,
            },
            description="Replace product_id with a real UUID from GET /products.",
        ),
    ],
)
class AddCartItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=999)
