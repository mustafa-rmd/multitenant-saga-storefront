from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ResourceNotFound
from apps.core.responses import envelope
from apps.payments.gateways import registry
from apps.payments.models import PaymentGatewayConfig
from apps.payments.models.gateway_name import GatewayName
from apps.payments.services import build_credentials


class PublicGatewayDetailView(APIView):
    """Detail for one gateway, scoped to the resolved tenant.

    Returns the same `name` / `displayName` / `isDefault` as the list
    endpoint, plus the gateway's capabilities (`supportedCurrencies`,
    `tokenization`, `supports3ds`) and any client-safe public credentials
    (e.g. Stripe's `publishableKey`) the storefront SDK needs.

    `mock` is hidden by the `PAYMENTS_ALLOW_MOCK_GATEWAY` flag — same
    behaviour as the list endpoint, so a client iterating the list can
    safely fetch each detail without surprises.

    Returns 404 rather than 409 here (the list endpoint is the discovery
    contract; anything not in the list shouldn't exist as a detail).
    """

    @extend_schema(summary="Get one payment gateway's capabilities for this tenant")
    def get(self, request, gateway_name: str):
        if gateway_name == GatewayName.MOCK and not settings.PAYMENTS_ALLOW_MOCK_GATEWAY:
            raise ResourceNotFound(f"Gateway '{gateway_name}' is not available")

        try:
            config = PaymentGatewayConfig.objects.get(
                gateway_name=gateway_name,
                is_active=True,
            )
        except PaymentGatewayConfig.DoesNotExist as e:
            raise ResourceNotFound(
                f"Gateway '{gateway_name}' is not configured for this tenant"
            ) from e

        gateway = registry.get(config.gateway_name)
        credentials = build_credentials(config)
        caps = gateway.describe(credentials=credentials)

        try:
            display_name = GatewayName(config.gateway_name).label
        except ValueError:
            display_name = config.gateway_name

        return Response(
            envelope(
                {
                    "name": config.gateway_name,
                    "display_name": display_name,
                    "is_default": config.is_default,
                    "supported_currencies": caps.supported_currencies,
                    "tokenization": caps.tokenization,
                    "supports_3ds": caps.supports_3ds,
                    "public_credentials": caps.public_credentials,
                },
                request=request,
            )
        )
