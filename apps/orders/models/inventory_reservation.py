from django.db import models

from apps.core.models import TenantScopedModel
from apps.orders.models.order import Order
from apps.orders.models.reservation_status import ReservationStatus


class InventoryReservation(TenantScopedModel):
    """Holds stock during checkout. Has a TTL after which the beat task
    releases it back to the product."""

    cart = models.ForeignKey("carts.Cart", on_delete=models.PROTECT, related_name="reservations")
    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reservations",
    )
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    quantity = models.IntegerField()
    expires_at = models.DateTimeField()
    status = models.CharField(
        max_length=16,
        choices=ReservationStatus.choices,
        default=ReservationStatus.ACTIVE,
    )

    Status = ReservationStatus

    class Meta:
        db_table = "orders_inventoryreservation"
        indexes = [
            models.Index(fields=["status", "expires_at"], name="orders_inve_status_expires_idx"),
            models.Index(fields=["tenant", "cart"], name="orders_inve_tenant_cart_idx"),
        ]
