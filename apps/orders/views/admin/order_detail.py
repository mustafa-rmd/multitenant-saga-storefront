from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.response import Response

from apps.core.exceptions import ResourceNotFound
from apps.core.responses import envelope
from apps.iam.views._base import TenantAdminAPIView
from apps.orders.models import Order
from apps.orders.serializers import AdminOrderSerializer


@extend_schema_view(
    get=extend_schema(
        summary="Get any order in the tenant (admin)", responses={200: AdminOrderSerializer}
    ),
)
class AdminOrderDetailView(TenantAdminAPIView):
    """Tenant admins can fetch any order in their tenant for support; the
    storefront `OrderDetailView` is filtered to the calling customer's
    own orders.

    Uses `AdminOrderSerializer` so the response includes the linked
    Payment attempts (with gateway transaction ids) and Invoice -- the
    operator-facing extras the customer-side serializer hides.
    """

    serializer_class = AdminOrderSerializer
    lookup_url_kwarg = "order_id"

    def get(self, request, order_id):
        try:
            order = (
                Order.objects.select_related("invoice")
                .prefetch_related("items", "payments__gateway_config")
                .get(id=order_id)
            )
        except Order.DoesNotExist as exc:
            raise ResourceNotFound("Order not found") from exc
        return Response(envelope(AdminOrderSerializer(order).data, request=request))
