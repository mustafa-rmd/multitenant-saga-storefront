from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics

from apps.orders.models import Order
from apps.orders.serializers import OrderSerializer


@extend_schema_view(get=extend_schema(summary="Get order detail"))
class OrderDetailView(generics.RetrieveAPIView):
    """Retrieve a single order owned by the authenticated customer.

    Filtered to `customer_id = request.user.id` so orders belonging to
    another customer in the same tenant return `404` (not `403` — we
    don't acknowledge existence). Cross-tenant access is impossible at
    two layers: the manager filter and Postgres RLS.

    Returns the full order: line items with snapshotted prices, totals
    breakdown, `status` (pending / paid / failed / cancelled), the
    `order_number` (sequential per tenant from a dedicated Postgres
    sequence), snapshotted shipping and billing address blobs, and B2B
    fields if present. The invoice (if any) is fetched separately via
    `/orders/{id}/invoice`.

    Currently returns the bare model (not the standard envelope) — clients
    should accept both shapes.
    """

    serializer_class = OrderSerializer
    lookup_url_kwarg = "order_id"

    def get_queryset(self):
        return Order.objects.filter(customer_id=self.request.user.id)
