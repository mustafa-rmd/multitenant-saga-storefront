from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Checkout (no extra metadata)",
            value={"payment_metadata": {}},
            description=(
                "payment_metadata is forwarded to the gateway. Required "
                "headers: Idempotency-Key (any unique string per attempt); "
                "optionally If-Match: <cart.version> for optimistic locking."
            ),
        ),
    ],
)
class CheckoutSerializer(serializers.Serializer):
    payment_metadata = serializers.DictField(required=False, default=dict)
