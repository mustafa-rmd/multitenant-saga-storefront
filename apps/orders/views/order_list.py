from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view
from rest_framework import generics

from apps.orders.models import Order
from apps.orders.serializers import OrderSerializer


@extend_schema_view(
    get=extend_schema(
        summary="List the customer's orders",
        parameters=[
            OpenApiParameter(
                "status",
                OpenApiTypes.STR,
                description=(
                    "Filter by order status: `pending`, `paid`, `fulfilled`, "
                    "`cancelled`, `refunded`. Omit to return all statuses."
                ),
            ),
            OpenApiParameter(
                "page",
                OpenApiTypes.INT,
                description="Page number for pagination (1-based). Defaults to 1.",
            ),
            OpenApiParameter(
                "page_size",
                OpenApiTypes.INT,
                description="Page size. Defaults to 20, max 100.",
            ),
        ],
    )
)
class OrderListView(generics.ListAPIView):
    """List the authenticated customer's orders, newest first.

    Filtered to `customer_id = request.user.id` — cross-customer access
    is impossible (manager filter + Postgres RLS). Results ordered by
    `-created_at` (most recent first). Use the standard `page` /
    `page_size` query params for pagination; the response envelope
    includes `meta.pagination` with next/previous cursors.

    Optional `?status=<value>` narrows to a single status — typical
    queries: `?status=pending` for orders in flight, `?status=paid` for
    history. Unknown status values return an empty page (not 400) since
    they can't match anything.
    """

    serializer_class = OrderSerializer

    def get_queryset(self):
        qs = Order.objects.filter(customer_id=self.request.user.id)
        if status := self.request.query_params.get("status"):
            qs = qs.filter(status=status)
        return qs
