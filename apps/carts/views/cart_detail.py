from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.carts.serializers import CartSerializer
from apps.carts.services import CartService
from apps.core.responses import envelope


class CartDetailView(APIView):
    """Get or abandon the authenticated customer's active cart."""

    @extend_schema(summary="Get the customer's cart")
    def get(self, request):
        """Retrieve the authenticated customer's active cart.

        The cart is implicit — there is no `cart_id` in the URL because
        each customer has exactly one persistent cart per tenant, resolved
        from `X-Customer-Id`. If the customer has never added an item, an
        empty cart is returned (it is not persisted until the first add).

        Response includes line items with snapshotted unit prices, applied
        coupons, shipping/billing address and payment-method slots, the
        locked-in currency (set on first add), and the totals breakdown
        (subtotal, discount, shipping, grandTotal). The `version` field
        bumps on every mutation — pass it back as `If-Match` on checkout
        for optimistic concurrency.
        """
        cart = CartService.get_cart(customer_id=request.user.id)
        return Response(envelope(CartSerializer(cart).data, request=request))

    @extend_schema(summary="Abandon (clear) the active cart")
    def delete(self, request):
        """Abandon the customer's active cart.

        Empties items + coupons, releases the address and payment-method
        slot references, unlocks the currency, and marks the cart
        `abandoned`. Idempotent: calling with no active cart returns
        `204` without raising. The next `POST /cart/items` lazy-creates
        a fresh active cart, so this is non-destructive — the user just
        loses their pending selections.

        Returns `204 No Content`. Carts in `checking_out` or `converted`
        status are not affected (the saga owns those).
        """
        CartService.clear_cart(customer_id=request.user.id)
        return Response(status=status.HTTP_204_NO_CONTENT)
