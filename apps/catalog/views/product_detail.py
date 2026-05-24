from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics

from apps.catalog.models import Product
from apps.catalog.serializers import ProductSerializer


@extend_schema_view(get=extend_schema(summary="Get product detail"))
class ProductDetailView(generics.RetrieveAPIView):
    """Retrieve a single product on the resolved tenant.

    Returns `404` if the product is inactive (`is_active=False`) or belongs
    to a different tenant — the manager filter and Postgres RLS keep
    cross-tenant access impossible. The full serializer is returned:
    `sku`, `name`, `description`, `price`, `currency`, `stockQuantity`,
    `availableQuantity`, `isActive`, `imageUrl`. `reservedQuantity` is
    intentionally not exposed here — admin clients can read it from the
    admin product surface.

    Use this for product pages and to look up the canonical price /
    currency before adding to cart. The cart still snapshots the unit
    price at add-time, so reading this endpoint and then adding within
    the same session does not guarantee the same price the cart will
    record.
    """

    serializer_class = ProductSerializer
    lookup_url_kwarg = "product_id"

    def get_queryset(self):
        return Product.objects.filter(is_active=True)
