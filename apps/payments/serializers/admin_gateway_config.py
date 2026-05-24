from rest_framework import serializers

from apps.payments.models import PaymentGatewayConfig


class AdminGatewayConfigSerializer(serializers.ModelSerializer):
    """Returns credentials redacted in list views; tenant-admins see them
    in detail views because they are the ones who set them."""

    class Meta:
        model = PaymentGatewayConfig
        fields = [
            "id",
            "gateway_name",
            "credentials",
            "is_active",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AdminGatewayConfigUpsertSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentGatewayConfig
        fields = ["gateway_name", "credentials", "is_active", "is_default"]
