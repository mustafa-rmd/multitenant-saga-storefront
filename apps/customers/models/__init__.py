"""
Customer and Address models.

The Customer row is the application's identity record (orders, addresses,
B2B status). Authentication is handled at the edge: an upstream identity
proxy validates the customer's session and sets X-Customer-Id, which
CustomerAuthMiddleware resolves to a Customer row (RLS-scoped, so cross-
tenant IDs return 404).
"""

from apps.customers.models.address import Address
from apps.customers.models.address_label import AddressLabel
from apps.customers.models.customer import Customer
from apps.customers.models.customer_type import CustomerType

__all__ = ["CustomerType", "Customer", "AddressLabel", "Address"]
