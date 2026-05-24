from rest_framework import serializers

from apps.payments.models import PaymentGatewayConfig
from apps.payments.models.gateway_name import GatewayName


class PublicGatewaySerializer(serializers.ModelSerializer):
    """Customer-safe projection of a `PaymentGatewayConfig`.

    Deliberately omits the `credentials` JSONB (secrets) and the FK ids
    that customers shouldn't need to handle. `displayName` comes from
    `GatewayName.label` so it stays in sync with the enum.
    """

    display_name = serializers.SerializerMethodField()

    class Meta:
        model = PaymentGatewayConfig
        fields = ("name", "display_name", "is_default")

    name = serializers.CharField(source="gateway_name")

    def get_display_name(self, obj: PaymentGatewayConfig) -> str:
        try:
            return GatewayName(obj.gateway_name).label
        except ValueError:
            return obj.gateway_name
