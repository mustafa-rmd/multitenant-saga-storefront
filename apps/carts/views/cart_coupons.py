from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.carts.serializers import ApplyCouponSerializer, CartSerializer
from apps.carts.services import CartService
from apps.core.responses import envelope


class CartCouponsView(APIView):
    """Apply a coupon code to the cart.

    Validates every constraint dimension before applying: existence on the
    current tenant, validity window (`valid_from` / `valid_until`),
    `max_uses` cap, minimum subtotal, allowed shipping countries, and the
    `B2C` / `B2B` customer-type restriction. Percent discounts are capped
    at the cart subtotal so the grand total cannot go negative.

    Possible failures: `404 coupon_not_found`, `409 coupon_already_applied`,
    `409 coupon_min_not_met`, `409 coupon_country_restricted`,
    `409 coupon_exhausted`, `410 coupon_expired`. Returns the updated cart
    on success.
    """

    @extend_schema(summary="Apply a coupon to the cart")
    def post(self, request):
        s = ApplyCouponSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        cart = CartService.apply_coupon(
            customer_id=request.user.id,
            code=s.validated_data["code"],
        )
        return Response(envelope(CartSerializer(cart).data, request=request))
