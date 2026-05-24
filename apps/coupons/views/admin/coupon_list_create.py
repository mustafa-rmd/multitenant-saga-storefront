from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.response import Response

from apps.core.responses import envelope
from apps.coupons.models import Coupon
from apps.coupons.serializers_admin import (
    AdminCouponCreateSerializer,
    AdminCouponSerializer,
)
from apps.iam.views._base import TenantAdminAPIView


@extend_schema_view(
    get=extend_schema(
        summary="List coupons (admin)", responses={200: AdminCouponSerializer(many=True)}
    ),
    post=extend_schema(
        summary="Create a coupon",
        request=AdminCouponCreateSerializer,
        responses={201: AdminCouponSerializer},
    ),
)
class AdminCouponListCreateView(TenantAdminAPIView):
    serializer_class = AdminCouponSerializer

    def get_queryset(self):
        return Coupon.objects.all().order_by("code")

    def get(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(AdminCouponSerializer(page, many=True).data)
        return Response(envelope(AdminCouponSerializer(qs, many=True).data, request=request))

    def post(self, request):
        s = AdminCouponCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        coupon = Coupon.objects.create(**s.validated_data)
        return Response(
            envelope(AdminCouponSerializer(coupon).data, request=request),
            status=status.HTTP_201_CREATED,
        )
