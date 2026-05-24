from django.urls import path

from apps.catalog import views

urlpatterns = [
    path("products", views.ProductListView.as_view(), name="product-list"),
    path("products/<uuid:product_id>", views.ProductDetailView.as_view(), name="product-detail"),
]
