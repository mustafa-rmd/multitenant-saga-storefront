from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.carts.serializers import AddCartItemSerializer, CartSerializer
from apps.carts.services import CartService
from apps.core.responses import envelope


class CartItemsView(APIView):
    """Add a product to the cart (or increment its quantity).

    Lazy-creates the cart on the first add. Re-adding the same product
    increments the existing line's quantity rather than creating a new
    line. The unit price is **snapshotted at add time** so the total stays
    stable as the customer browses — later catalog price changes do not
    silently re-price the cart.

    The first add locks the cart's currency to the product's currency.
    Subsequent adds of products in a different currency are rejected with
    `409 currency_mismatch`. If the requested quantity exceeds available
    stock (`stock_quantity - reserved_quantity`), the response is
    `409 insufficient_stock`.

    Returns the full cart envelope so clients don't need a follow-up GET.
    """

    @extend_schema(summary="Add a product to the cart")
    def post(self, request):
        s = AddCartItemSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        cart = CartService.add_item(
            customer_id=request.user.id,
            product_id=s.validated_data["product_id"],
            quantity=s.validated_data["quantity"],
        )
        return Response(
            envelope(CartSerializer(cart).data, request=request),
            status=status.HTTP_200_OK,
        )
