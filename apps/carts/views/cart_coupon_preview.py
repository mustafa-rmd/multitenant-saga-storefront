from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.carts.serializers import ApplyCouponSerializer
from apps.carts.services import CartService
from apps.core.responses import envelope


class CartCouponPreviewView(APIView):
    """Validate a coupon code against the current cart without applying it."""

    @extend_schema(
        summary="Preview a coupon (no side effects)",
        request=ApplyCouponSerializer,
    )
    def post(self, request):
        """Dry-run validation of a coupon against the customer's active cart.

        Runs the same constraint checks the real `POST /cart/coupons`
        endpoint runs (min subtotal, expiry, max_uses, country
        restriction, customer-type restriction, currency match), but
        never persists an `AppliedCoupon` and never bumps cart version.

        Useful for cart-edit UIs that want to surface "Apply" / "Invalid"
        feedback live as the user types a code, without committing the
        cart to a coupon they might decide against.

        Success response (`200`) shape:
        ```
        {
          "valid": true,
          "code": "WELCOME10",
          "alreadyApplied": false,
          "discount": "30.00",
          "projectedDiscountTotal": "30.00",
          "projectedGrandTotal": "269.97",
          "currency": "SAR"
        }
        ```

        Failures return the same error envelope codes as apply:
        `coupon_not_found`, `coupon_invalid`, `coupon_expired`,
        `coupon_exhausted`, `coupon_min_not_met`,
        `coupon_country_restricted`. `alreadyApplied=true` is the only
        case where the coupon is technically valid but applying it would
        be a no-op (a second `apply` would 409); this is `200` with a
        flag, not an error, so UIs can render "already on your cart"
        instead of a generic "invalid".
        """
        s = ApplyCouponSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        preview = CartService.preview_coupon(
            customer_id=request.user.id,
            code=s.validated_data["code"],
        )
        return Response(envelope(preview, request=request))
