"""Shared helpers for admin Product views.

Pulling `_get` out of the per-view classes keeps them focused on HTTP
handling and means a future product subresource (e.g. variants, tags)
inherits the same not-found semantics for free.
"""

from apps.catalog.models import Product
from apps.core.exceptions import ResourceNotFound


class ProductLookupMixin:
    """Resolve a Product by UUID with tenant scoping inherited from the manager.

    Raises `ResourceNotFound` (→ 404) on miss; the alternative bare
    `DoesNotExist` would surface as a generic 500.
    """

    def _get_product(self, product_id) -> Product:
        try:
            return Product.objects.get(id=product_id)
        except Product.DoesNotExist as exc:
            raise ResourceNotFound("Product not found") from exc
