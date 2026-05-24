from rest_framework import serializers

from apps.payments.models import Payment


class AdminPaymentSerializer(serializers.ModelSerializer):
    """Operator-facing projection of a `Payment` row.

    Wider than any customer-facing serializer:
      * `gatewayName` is flattened in from the linked PaymentGatewayConfig
        so an operator can see which gateway took the money without a
        second lookup.
      * `gatewayTransactionId` is exposed verbatim — that's the id an
        operator pastes into the Stripe/HyperPay dashboard to reconcile.
      * `gatewayResponse` (the raw JSONB from the gateway) is included
        for forensic debugging. It is NOT customer-safe — failure codes,
        last4, sometimes IP addresses live in here — but admin auth +
        RLS + TLS make this acceptable behind the admin rail.

    Used both nested under `AdminOrderSerializer.payments` and standalone
    by `AdminOrderPaymentListView`.
    """

    gateway_name = serializers.SerializerMethodField()

    def get_gateway_name(self, obj) -> str | None:
        # gateway_config is nullable for PO payments (no gateway involved).
        if obj.gateway_config_id is None:
            return None
        return obj.gateway_config.gateway_name

    class Meta:
        model = Payment
        fields = [
            "id",
            "status",
            "amount",
            "currency",
            "gateway_name",
            "gateway_transaction_id",
            "idempotency_key",
            "gateway_response",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
