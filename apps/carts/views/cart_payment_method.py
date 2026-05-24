from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.carts.serializers import CartSerializer, SetSlotSerializer
from apps.carts.services import CartService
from apps.core.responses import envelope


class CartPaymentMethodView(APIView):
    """Select which saved payment method this cart will use at checkout.

    Body: `{"id": "<payment-method-uuid>"}`. The payment method must belong
    to the authenticated customer. The gateway is resolved transitively via
    `PaymentMethod.gateway_config`, so the cart implicitly picks the
    gateway too. Required before checkout.

    If the gateway doesn't support the cart's locked-in currency, checkout
    will fail with `409 gateway_unsupported_currency` — this PUT does not
    pre-validate currency support.
    """

    @extend_schema(summary="Select the cart's payment method")
    def put(self, request):
        s = SetSlotSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        cart = CartService.set_payment_method(
            customer_id=request.user.id,
            payment_method_id=s.validated_data["id"],
        )
        return Response(envelope(CartSerializer(cart).data, request=request))
