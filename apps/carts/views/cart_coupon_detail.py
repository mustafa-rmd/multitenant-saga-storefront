from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.carts.serializers import CartSerializer
from apps.carts.services import CartService
from apps.core.responses import envelope


class CartCouponDetailView(APIView):
    """Remove a previously applied coupon from the cart.

    Idempotent — removing a coupon that was never applied (or has already
    been removed) returns the cart unchanged with a `404 coupon_not_found`
    only when the code itself is unknown on this tenant. The cart totals
    recompute on removal.
    """

    @extend_schema(summary="Remove a coupon from the cart")
    def delete(self, request, code):
        cart = CartService.remove_coupon(
            customer_id=request.user.id,
            code=code,
        )
        return Response(envelope(CartSerializer(cart).data, request=request))
