from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view
from rest_framework.response import Response

from apps.core.responses import envelope
from apps.iam.views._base import TenantAdminAPIView
from apps.orders.models import Order
from apps.orders.serializers import AdminOrderSerializer


@extend_schema_view(
    get=extend_schema(
        summary="List all orders in the tenant (admin)",
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, description="Filter by order status."),
            OpenApiParameter(
                "customer_id", OpenApiTypes.UUID, description="Filter to one customer."
            ),
        ],
        responses={200: AdminOrderSerializer(many=True)},
    ),
)
class AdminOrderListView(TenantAdminAPIView):
    """List every order in the resolved tenant. Storefront `OrderListView`
    filters by `customer_id=request.user.id`; this one removes that filter
    because tenant admins need cross-customer visibility for support.

    Uses `AdminOrderSerializer` so each list row already carries payment
    + invoice status -- an operator can scan a screen of orders and spot
    the ones stuck in `paid` with an empty `invoice.pdfUrl` (Celery task
    needs attention) without N+1 follow-up requests.
    """

    serializer_class = AdminOrderSerializer

    def get_queryset(self):
        qs = (
            Order.objects.select_related("invoice")
            .prefetch_related("items", "payments__gateway_config")
            .all()
        )
        params = self.request.query_params
        if status_param := params.get("status"):
            qs = qs.filter(status=status_param)
        if customer_id := params.get("customer_id"):
            qs = qs.filter(customer_id=customer_id)
        return qs

    def get(self, request):
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(AdminOrderSerializer(page, many=True).data)
        return Response(envelope(AdminOrderSerializer(qs, many=True).data, request=request))
