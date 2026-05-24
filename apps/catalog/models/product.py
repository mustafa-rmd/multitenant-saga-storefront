"""
Product model.

`stock_quantity` is physical inventory; only decremented when a payment
is captured. `reserved_quantity` is held by active InventoryReservations
(see apps/orders/models/inventory_reservation.py). Available = stock - reserved.

The available_quantity property reads both columns, but for correctness
under concurrency you should always be inside a transaction that has
SELECT FOR UPDATE'd the product row before reading them.
"""

from django.db import models

from apps.core.models import TenantScopedModel


class Product(TenantScopedModel):
    sku = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    stock_quantity = models.IntegerField(default=0)
    reserved_quantity = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    # Object-storage key (e.g. "tenants/<uuid>/products/<uuid>/main.png").
    # The actual URL is derived via storages['media'].url(image_key) -- keeps
    # the row stable across endpoint / region / S3-vs-MinIO moves. Empty
    # string means no image; the admin upload endpoint writes the key.
    image_key = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "catalog_product"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "sku"],
                name="uniq_product_sku_per_tenant",
            ),
            models.CheckConstraint(
                check=models.Q(stock_quantity__gte=models.F("reserved_quantity")),
                name="stock_gte_reserved",
            ),
            models.CheckConstraint(
                check=models.Q(price__gte=0),
                name="price_non_negative",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "is_active"], name="catalog_pro_tenant__idx"),
        ]

    def __str__(self):
        return f"{self.sku} -- {self.name}"

    @property
    def available_quantity(self) -> int:
        return self.stock_quantity - self.reserved_quantity

    @property
    def image_url(self) -> str:
        """Public URL for the primary image, or "" if none. Computed lazily
        because storages['media'].url() builds the URL from the backend's
        current endpoint config."""
        if not self.image_key:
            return ""
        from django.core.files.storage import storages

        return storages["media"].url(self.image_key)
