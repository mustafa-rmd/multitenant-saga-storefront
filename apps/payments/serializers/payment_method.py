from rest_framework import serializers

from apps.payments.models import PaymentMethod


class PaymentMethodSerializer(serializers.ModelSerializer):
    """Read-only representation of a saved payment method.

    Card variant exposes `brand` / `last_four`; PO variant exposes
    `payment_terms` / `po_account_label`. `gateway_name` is nullable
    because PO methods don't bind a gateway.
    """

    gateway_name = serializers.SerializerMethodField()

    class Meta:
        model = PaymentMethod
        fields = [
            "id",
            "method_type",
            "gateway_name",
            "brand",
            "last_four",
            "payment_terms",
            "po_account_label",
            "is_default",
            "created_at",
        ]
        read_only_fields = fields

    def get_gateway_name(self, obj) -> str | None:
        if obj.gateway_config_id is None:
            return None
        return obj.gateway_config.gateway_name
