"""Storefront customer-scoped views (address CRUD against the
authenticated X-Customer-Id). Tenant-admin and platform-admin surfaces
live under views/admin/."""

from apps.customers.views.customer_address_detail import CustomerAddressDetailView
from apps.customers.views.customer_address_list_create import CustomerAddressListCreateView

__all__ = ["CustomerAddressDetailView", "CustomerAddressListCreateView"]
