"""Read-only catalog views. Catalog management is out of scope (admin only)."""

from apps.catalog.views.product_detail import ProductDetailView
from apps.catalog.views.product_list import ProductListView

__all__ = ["ProductDetailView", "ProductListView"]
