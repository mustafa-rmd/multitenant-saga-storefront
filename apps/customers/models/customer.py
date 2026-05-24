from django.db import models

from apps.core.models import TenantScopedModel
from apps.customers.models.customer_type import CustomerType


class Customer(TenantScopedModel):
    email = models.EmailField()
    name = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    customer_type = models.CharField(
        max_length=4,
        choices=CustomerType.choices,
        default=CustomerType.B2C,
    )
    # B2B fields
    tax_id = models.CharField(max_length=64, blank=True)
    company_name = models.CharField(max_length=255, blank=True)
    # Soft-delete / block flag. When False, CustomerAuthMiddleware refuses
    # the X-Customer-Id header (returns 401 customer_not_found, no
    # enumeration). Existing orders / addresses / carts are preserved.
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "customers_customer"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "email"],
                name="uniq_customer_email_per_tenant",
            ),
        ]

    def __str__(self):
        return self.email

    @property
    def is_b2b(self) -> bool:
        return self.customer_type == CustomerType.B2B
