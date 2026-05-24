from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.response import Response

from apps.core.responses import envelope
from apps.payments.models import PaymentGatewayConfig
from apps.payments.models.gateway_name import GatewayName
from apps.payments.serializers.public_gateway import PublicGatewaySerializer


class PublicGatewayListView(generics.ListAPIView):
    """List the payment gateways available to the current tenant's storefront.

    Returns only `is_active=True` configs, with the `mock` gateway hidden
    in any environment where `PAYMENTS_ALLOW_MOCK_GATEWAY` is off
    (default in prod). Storefronts call this to decide which payment
    forms / SDKs to render before a customer reaches checkout.

    Secrets (credentials JSONB, raw FK ids) are intentionally not in the
    response shape -- the admin endpoint under `/admin/payment-gateways`
    is the place to manage those.
    """

    serializer_class = PublicGatewaySerializer

    def get_queryset(self):
        qs = PaymentGatewayConfig.objects.filter(is_active=True).order_by(
            "-is_default", "gateway_name"
        )
        if not settings.PAYMENTS_ALLOW_MOCK_GATEWAY:
            qs = qs.exclude(gateway_name=GatewayName.MOCK)
        return qs

    @extend_schema(summary="List active payment gateways for this tenant")
    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()
        data = self.get_serializer(qs, many=True).data
        return Response(envelope(data, request=request))
