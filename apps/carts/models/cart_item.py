"""
CartItem.unit_price_snapshot freezes the price at add-time. This is a
deliberate trade-off documented in the README: predictable customer
experience vs. always-current pricing. The price is re-validated at
checkout against the live Product price (within tolerance, currently
not enforced -- TODO).
"""

from django.db import models

from apps.carts.models.cart import Cart
from apps.core.models import TenantScopedModel


class CartItem(TenantScopedModel):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    quantity = models.IntegerField()
    unit_price_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)

    class Meta:
        db_table = "carts_cartitem"
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product"],
                name="uniq_product_per_cart",
            ),
            models.CheckConstraint(
                check=models.Q(quantity__gte=1),
                name="cart_item_quantity_positive",
            ),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.product_id}"

    @property
    def line_total(self):
        return self.unit_price_snapshot * self.quantity
