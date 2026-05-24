from django.urls import path

from apps.catalog.views.admin import (
    AdminProductDetailView,
    AdminProductImageView,
    AdminProductListCreateView,
)

urlpatterns = [
    path("products", AdminProductListCreateView.as_view(), name="admin-product-list-create"),
    path(
        "products/<uuid:product_id>",
        AdminProductDetailView.as_view(),
        name="admin-product-detail",
    ),
    path(
        "products/<uuid:product_id>/image",
        AdminProductImageView.as_view(),
        name="admin-product-image",
    ),
]
