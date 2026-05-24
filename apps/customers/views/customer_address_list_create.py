from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics

from apps.core.exceptions import Forbidden
from apps.customers.models import Address
from apps.customers.serializers import AddressSerializer


@extend_schema_view(
    get=extend_schema(summary="List the customer's saved addresses"),
    post=extend_schema(summary="Add a saved address"),
)
class CustomerAddressListCreateView(generics.ListCreateAPIView):
    """List and create saved addresses for the authenticated customer.

    The `{customer_id}` in the path must match the `X-Customer-Id` header
    — a customer can only manage their own addresses (`403 forbidden`
    otherwise). All addresses are tenant-scoped: they live in the resolved
    tenant and are only usable from carts in that tenant.

    `GET` returns the customer's address book (no pagination needed —
    customers rarely have more than a handful). `POST` creates a new
    address; setting `isDefault: true` does NOT clear other defaults
    here, since address "default" is informational only (`Cart` always
    references an explicit address slot by id).

    These endpoints use DRF generic views directly and return the bare
    model rather than the standard envelope — clients should accept both
    shapes: `id = body.data?.id ?? body.id`.
    """

    serializer_class = AddressSerializer

    def get_queryset(self):
        customer_id = self.kwargs["customer_id"]
        if str(self.request.user.id) != str(customer_id):
            raise Forbidden("You can only access your own addresses")
        return Address.objects.filter(customer_id=customer_id).order_by("-is_default", "city")

    def perform_create(self, serializer):
        customer_id = self.kwargs["customer_id"]
        if str(self.request.user.id) != str(customer_id):
            raise Forbidden("You can only access your own addresses")
        serializer.save(customer_id=customer_id)
