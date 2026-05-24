from django.urls import path

from apps.customers import views

urlpatterns = [
    path(
        "customers/<uuid:customer_id>/addresses",
        views.CustomerAddressListCreateView.as_view(),
        name="customer-address-list-create",
    ),
    path(
        "customers/<uuid:customer_id>/addresses/<uuid:address_id>",
        views.CustomerAddressDetailView.as_view(),
        name="customer-address-detail",
    ),
]
