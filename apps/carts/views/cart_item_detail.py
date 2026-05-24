from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.carts.serializers import CartSerializer, UpdateCartItemSerializer
from apps.carts.services import CartService
from apps.core.responses import envelope


class CartItemDetailView(APIView):
    """Per-line cart operations: update quantity, remove."""

    @extend_schema(
        summary="Update a cart line's quantity",
        request=UpdateCartItemSerializer,
        responses={200: None},
    )
    def patch(self, request, item_id):
        """Replace the line's quantity with the value in the request body.

        Body: `{"quantity": <int>}` (1–999). Unlike `POST /cart/items`,
        which merges by incrementing the existing line, PATCH **replaces**
        the quantity — useful for cart-edit UIs ("set to 3", not "add 3
        more"). Quantity `0` is not allowed; use `DELETE
        /cart/items/{item_id}` for that.

        Stock check applies (`409 insufficient_stock` if `quantity` exceeds
        `availableQuantity`). Returns the full cart with updated totals
        and bumped `version`.
        """
        s = UpdateCartItemSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        cart = CartService.update_item_quantity(
            customer_id=request.user.id,
            item_id=item_id,
            quantity=s.validated_data["quantity"],
        )
        return Response(envelope(CartSerializer(cart).data, request=request))

    @extend_schema(summary="Remove a line from the cart")
    def delete(self, request, item_id):
        """Remove a single line from the cart.

        Removes the entire line regardless of quantity (there is no
        "decrement by N" endpoint — use PATCH to set a smaller quantity,
        or DELETE then re-POST). Removing the last line clears the
        currency lock, so the next add can be in any currency. Returns
        the full updated cart.
        """
        cart = CartService.remove_item(
            customer_id=request.user.id,
            item_id=item_id,
        )
        return Response(envelope(CartSerializer(cart).data, request=request))
