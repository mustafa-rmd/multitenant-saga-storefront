from django.db import models

from apps.core.models import TenantScopedModel
from apps.customers.models.address_label import AddressLabel
from apps.customers.models.customer import Customer


class Address(TenantScopedModel):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="addresses")
    label = models.CharField(
        max_length=16,
        choices=AddressLabel.choices,
        default=AddressLabel.BOTH,
    )
    country = models.CharField(max_length=2)  # ISO 3166-1 alpha-2
    city = models.CharField(max_length=255)
    street = models.CharField(max_length=255)
    postal_code = models.CharField(max_length=32, blank=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "customers_address"
        indexes = [
            models.Index(fields=["tenant", "customer"], name="customers_a_tenant__idx"),
        ]

    def __str__(self):
        return f"{self.street}, {self.city}, {self.country}"

    def to_snapshot(self) -> dict:
        """Frozen representation for snapshotting onto Order."""
        return {
            "country": self.country,
            "city": self.city,
            "street": self.street,
            "postal_code": self.postal_code,
        }
