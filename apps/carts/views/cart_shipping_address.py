from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.carts.serializers import CartSerializer, SetSlotSerializer
from apps.carts.services import CartService
from apps.core.responses import envelope


class CartShippingAddressView(APIView):
    """Set (or replace) the cart's shipping address slot.

    Body: `{"id": "<address-uuid>"}`. The address must belong to the
    authenticated customer on the resolved tenant — addresses are
    tenant-scoped via `TenantScopedModel`, and an address from a different
    customer or tenant returns `404`. Required before checkout.
    """

    @extend_schema(summary="Set the cart's shipping address")
    def put(self, request):
        s = SetSlotSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        cart = CartService.set_shipping_address(
            customer_id=request.user.id,
            address_id=s.validated_data["id"],
        )
        return Response(envelope(CartSerializer(cart).data, request=request))
