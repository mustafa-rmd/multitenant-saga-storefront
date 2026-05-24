from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Apply WELCOME10",
            value={"code": "WELCOME10"},
        ),
    ],
)
class ApplyCouponSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64)
