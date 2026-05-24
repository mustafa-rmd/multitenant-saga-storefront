from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics

from apps.core.exceptions import Forbidden
from apps.customers.models import Address
from apps.customers.serializers import AddressSerializer


@extend_schema_view(
    get=extend_schema(summary="Get a saved address"),
    put=extend_schema(summary="Replace a saved address"),
    patch=extend_schema(summary="Partially update a saved address"),
    delete=extend_schema(summary="Delete a saved address"),
)
class CustomerAddressDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a single saved address.

    The `{customer_id}` path segment must match `X-Customer-Id`
    (`403 forbidden` otherwise). The `{address_id}` is the address UUID.
    Addresses belonging to another customer (same tenant) or another
    tenant return `404` — we don't acknowledge existence across the
    ownership boundary.

    `DELETE` is a hard delete. Cart slots (shipping/billing) reference
    addresses with `on_delete=SET_NULL`, so deleting an address silently
    clears any active cart's slot that pointed at it -- the customer's
    next checkout attempt will return `cart_not_checkout_ready` until
    they pick a replacement. Orders snapshot their addresses, so
    deleting an address never affects historical orders.

    Returns the bare model (no envelope), consistent with the create
    endpoint.
    """

    serializer_class = AddressSerializer
    lookup_url_kwarg = "address_id"

    def get_queryset(self):
        customer_id = self.kwargs["customer_id"]
        if str(self.request.user.id) != str(customer_id):
            raise Forbidden("You can only access your own addresses")
        return Address.objects.filter(customer_id=customer_id)
