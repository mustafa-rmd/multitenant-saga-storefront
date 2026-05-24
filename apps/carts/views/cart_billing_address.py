from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.carts.serializers import CartSerializer, SetSlotSerializer
from apps.carts.services import CartService
from apps.core.responses import envelope


class CartBillingAddressView(APIView):
    """Set (or replace) the cart's billing address slot.

    Body: `{"id": "<address-uuid>"}`. Same ownership rules as the shipping
    slot — the address must belong to the authenticated customer. Billing
    address can be the same address as shipping; the cart references them
    independently so invoices reflect the actual billing party.
    """

    @extend_schema(summary="Set the cart's billing address")
    def put(self, request):
        s = SetSlotSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        cart = CartService.set_billing_address(
            customer_id=request.user.id,
            address_id=s.validated_data["id"],
        )
        return Response(envelope(CartSerializer(cart).data, request=request))
