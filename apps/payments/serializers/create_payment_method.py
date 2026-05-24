from rest_framework import serializers

from apps.payments.models.gateway_name import GatewayName
from apps.payments.models.payment_method_type import PaymentMethodType


class CreatePaymentMethodSerializer(serializers.Serializer):
    """
    Create a payment method.

    Two variants share this endpoint:

    * `method_type=card` (default) — tokenized via a gateway. For real
      Stripe, the client tokenizes via Stripe.js and sends us the token
      (pm_xxx). For the mock gateway, the client can send a payload that
      the gateway turns into a fake token.
    * `method_type=purchase_order` — B2B invoiced payment. No gateway, no
      token. Requires `payment_terms` (e.g. "net_30") and optionally
      `po_account_label` for display. Only B2B customers may create these
      — the view enforces this with a 403.
    """

    method_type = serializers.ChoiceField(
        choices=PaymentMethodType.choices,
        required=False,
        default=PaymentMethodType.CARD,
    )
    gateway_name = serializers.ChoiceField(
        choices=GatewayName.choices, required=False, allow_blank=True
    )
    token = serializers.CharField(required=False, allow_blank=True)
    brand = serializers.CharField(required=False, allow_blank=True, default="")
    last_four = serializers.CharField(required=False, allow_blank=True, default="")
    is_default = serializers.BooleanField(required=False, default=False)
    # PO-only
    payment_terms = serializers.ChoiceField(
        choices=["net_15", "net_30", "net_60", "net_90"],
        required=False,
        allow_blank=True,
    )
    po_account_label = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        method_type = attrs.get("method_type", PaymentMethodType.CARD)
        if method_type == PaymentMethodType.CARD:
            if not attrs.get("gateway_name"):
                raise serializers.ValidationError(
                    {"gateway_name": "Required for card payment methods."}
                )
        else:  # purchase_order
            if not attrs.get("payment_terms"):
                raise serializers.ValidationError(
                    {"payment_terms": "Required for purchase_order payment methods."}
                )
        return attrs
