from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.response import Response

from apps.core.exceptions import ResourceNotFound
from apps.core.responses import envelope
from apps.iam.views._base import TenantAdminAPIView
from apps.payments.models import PaymentGatewayConfig
from apps.payments.serializers.admin_gateway_config import (
    AdminGatewayConfigSerializer,
    AdminGatewayConfigUpsertSerializer,
)


@extend_schema_view(
    get=extend_schema(
        summary="Get a gateway config (admin)", responses={200: AdminGatewayConfigSerializer}
    ),
    patch=extend_schema(
        summary="Update a gateway config",
        request=AdminGatewayConfigUpsertSerializer,
        responses={200: AdminGatewayConfigSerializer},
    ),
    delete=extend_schema(summary="Delete a gateway config", responses={204: None}),
)
class AdminGatewayConfigDetailView(TenantAdminAPIView):
    serializer_class = AdminGatewayConfigSerializer
    lookup_url_kwarg = "config_id"

    def _get(self, config_id):
        try:
            return PaymentGatewayConfig.objects.get(id=config_id)
        except PaymentGatewayConfig.DoesNotExist as exc:
            raise ResourceNotFound("Gateway config not found") from exc

    def get(self, request, config_id):
        config = self._get(config_id)
        return Response(envelope(AdminGatewayConfigSerializer(config).data, request=request))

    def patch(self, request, config_id):
        config = self._get(config_id)
        s = AdminGatewayConfigUpsertSerializer(config, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            if s.validated_data.get("is_default", False):
                PaymentGatewayConfig.objects.filter(is_default=True).exclude(id=config.id).update(
                    is_default=False
                )
            s.save()
        return Response(envelope(AdminGatewayConfigSerializer(config).data, request=request))

    def delete(self, request, config_id):
        config = self._get(config_id)
        # Hard delete; PaymentMethod.gateway_config uses on_delete=PROTECT, so
        # configs with saved methods will 500 — that's the right behavior, the
        # tenant must migrate those methods before deletion.
        config.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
