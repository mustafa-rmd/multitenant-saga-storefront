from django.urls import path

from apps.customers.views.admin import (
    AdminCustomerDetailView,
    AdminCustomerListCreateView,
    PlatformCustomerListView,
)

urlpatterns = [
    # Tenant-admin: per-tenant customer CRUD.
    path("customers", AdminCustomerListCreateView.as_view(), name="admin-customer-list-create"),
    path(
        "customers/<uuid:customer_id>",
        AdminCustomerDetailView.as_view(),
        name="admin-customer-detail",
    ),
    # Platform-admin: cross-tenant customer search. Path lives under
    # /platform/ so it falls under GLOBAL_EXEMPT_PATHS and is hosted
    # by the `admin` subdomain.
    path(
        "platform/customers",
        PlatformCustomerListView.as_view(),
        name="platform-customer-list",
    ),
]
