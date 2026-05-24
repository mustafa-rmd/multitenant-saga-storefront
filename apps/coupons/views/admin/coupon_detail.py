from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers, status
from rest_framework.response import Response

from apps.carts.models import AppliedCoupon
from apps.carts.models.cart import Cart
from apps.core.exceptions import CouponNotFound
from apps.core.responses import envelope
from apps.coupons.models import Coupon
from apps.coupons.serializers_admin import (
    AdminCouponSerializer,
    AdminCouponUpdateSerializer,
)
from apps.iam.views._base import TenantAdminAPIView

_ACTIVE_CART_STATUSES = (Cart.Status.ACTIVE, Cart.Status.CHECKING_OUT)


@extend_schema_view(
    get=extend_schema(summary="Get a coupon (admin)", responses={200: AdminCouponSerializer}),
    patch=extend_schema(
        summary="Update a coupon",
        request=AdminCouponUpdateSerializer,
        responses={200: AdminCouponSerializer},
    ),
    delete=extend_schema(
        summary="Soft-delete a coupon (sets isActive=false)", responses={204: None}
    ),
)
class AdminCouponDetailView(TenantAdminAPIView):
    """GET/PATCH/DELETE one coupon. DELETE is soft (preserves order history).

    PATCH takes a row lock so cross-cart invariants (max_uses >= uses_count,
    currency/discount_type changes blocked while live carts reference the
    coupon, valid_until cannot be set into the past) are evaluated against
    a consistent snapshot.
    """

    serializer_class = AdminCouponSerializer
    lookup_url_kwarg = "coupon_id"

    def _get(self, coupon_id):
        try:
            return Coupon.objects.get(id=coupon_id)
        except Coupon.DoesNotExist as exc:
            raise CouponNotFound("Coupon not found") from exc

    def get(self, request, coupon_id):
        coupon = self._get(coupon_id)
        return Response(envelope(AdminCouponSerializer(coupon).data, request=request))

    def patch(self, request, coupon_id):
        with transaction.atomic():
            try:
                coupon = Coupon.objects.select_for_update().get(id=coupon_id)
            except Coupon.DoesNotExist as exc:
                raise CouponNotFound("Coupon not found") from exc

            s = AdminCouponUpdateSerializer(coupon, data=request.data, partial=True)
            s.is_valid(raise_exception=True)
            validated = s.validated_data

            # max_uses cannot drop below the current usage count.
            new_max_uses = validated.get("max_uses", coupon.max_uses)
            if new_max_uses is not None and new_max_uses < coupon.uses_count:
                raise serializers.ValidationError(
                    {
                        "max_uses": (
                            f"Cannot set max_uses ({new_max_uses}) below the current "
                            f"uses_count ({coupon.uses_count})."
                        )
                    }
                )

            # valid_until cannot be set in the past -- admins who want to
            # immediately stop new applications should set is_active=False.
            new_valid_until = validated.get("valid_until")
            if new_valid_until is not None and new_valid_until < timezone.now():
                raise serializers.ValidationError(
                    {
                        "valid_until": (
                            "Cannot set valid_until to a past timestamp. To stop "
                            "new applications immediately, set is_active=false."
                        )
                    }
                )

            # currency and discount_type changes are blocked while any active
            # or in-flight cart references this coupon. compute_discount and
            # validate() both read these on every cart re-read; changing them
            # mid-flight would silently re-price or break checkout.
            currency_changing = "currency" in validated and validated["currency"] != coupon.currency
            type_changing = (
                "discount_type" in validated and validated["discount_type"] != coupon.discount_type
            )
            if currency_changing or type_changing:
                in_use = AppliedCoupon.objects.filter(
                    coupon_id=coupon.id,
                    cart__status__in=_ACTIVE_CART_STATUSES,
                ).exists()
                if in_use:
                    field = "currency" if currency_changing else "discount_type"
                    raise serializers.ValidationError(
                        {
                            field: (
                                f"Cannot change {field} while the coupon is applied to "
                                "any active or in-flight cart."
                            )
                        }
                    )

            s.save()
            return Response(envelope(AdminCouponSerializer(coupon).data, request=request))

    def delete(self, request, coupon_id):
        coupon = self._get(coupon_id)
        if coupon.is_active:
            coupon.is_active = False
            coupon.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
