from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.response import Response

from apps.core.exceptions import ResourceNotFound
from apps.core.responses import envelope
from apps.iam.views._base import TenantAdminAPIView
from apps.orders.models import Order
from apps.payments.serializers.admin_payment import AdminPaymentSerializer


@extend_schema_view(
    get=extend_schema(
        summary="List all payment attempts for an order (admin)",
        responses={200: AdminPaymentSerializer(many=True)},
    ),
)
class AdminOrderPaymentListView(TenantAdminAPIView):
    """Every Payment row tied to one order, newest first.

    `AdminOrderDetailView` already nests payments, but a dedicated list
    endpoint matters when the order page is heavy (long item list, big
    addresses) and an operator just wants to see "did capture happen
    yet, what's the gateway txn id". It also gives a stable resource
    shape for future tooling: a script polling for payment state
    shouldn't have to parse a whole order envelope.

    Tenant scope is enforced by the default RLS-backed manager -- a
    cross-tenant `order_id` returns 404, not the wrong rows.
    """

    serializer_class = AdminPaymentSerializer
    lookup_url_kwarg = "order_id"

    def get(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist as exc:
            raise ResourceNotFound("Order not found") from exc

        qs = order.payments.select_related("gateway_config").order_by("-created_at")
        return Response(envelope(AdminPaymentSerializer(qs, many=True).data, request=request))
