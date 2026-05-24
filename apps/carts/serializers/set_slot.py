from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Bind by ID",
            value={"id": "00000000-0000-0000-0000-000000000000"},
            description=(
                "Replace id with a real UUID -- an address UUID for "
                "shipping/billing-address, a payment method UUID for "
                "payment-method."
            ),
        ),
    ],
)
class SetSlotSerializer(serializers.Serializer):
    id = serializers.UUIDField()
