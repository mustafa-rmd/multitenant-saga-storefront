from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.response import Response

from apps.core.responses import envelope
from apps.iam.views._base import TenantAdminAPIView
from apps.payments.models import PaymentGatewayConfig
from apps.payments.serializers.admin_gateway_config import (
    AdminGatewayConfigSerializer,
    AdminGatewayConfigUpsertSerializer,
)


@extend_schema_view(
    get=extend_schema(
        summary="List payment gateway configs (admin)",
        responses={200: AdminGatewayConfigSerializer(many=True)},
    ),
    post=extend_schema(
        summary="Create a payment gateway config",
        request=AdminGatewayConfigUpsertSerializer,
        responses={201: AdminGatewayConfigSerializer},
    ),
)
class AdminGatewayConfigListCreateView(TenantAdminAPIView):
    serializer_class = AdminGatewayConfigSerializer

    def get_queryset(self):
        return PaymentGatewayConfig.objects.all().order_by("gateway_name")

    def get(self, request):
        qs = self.get_queryset()
        return Response(envelope(AdminGatewayConfigSerializer(qs, many=True).data, request=request))

    def post(self, request):
        s = AdminGatewayConfigUpsertSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        with transaction.atomic():
            # Only one default per tenant. Clear the existing default if the
            # new row is marked default; the unique constraint would 500
            # otherwise.
            if v.get("is_default", False):
                PaymentGatewayConfig.objects.filter(is_default=True).update(is_default=False)
            config = PaymentGatewayConfig.objects.create(**v)
        return Response(
            envelope(AdminGatewayConfigSerializer(config).data, request=request),
            status=status.HTTP_201_CREATED,
        )
