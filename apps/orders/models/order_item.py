from django.db import models

from apps.core.models import TenantScopedModel
from apps.orders.models.order import Order


class OrderItem(TenantScopedModel):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    product_sku_snapshot = models.CharField(max_length=64)
    product_name_snapshot = models.CharField(max_length=255)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)

    class Meta:
        db_table = "orders_orderitem"
