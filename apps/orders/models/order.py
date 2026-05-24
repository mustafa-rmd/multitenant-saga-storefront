from django.db import models

from apps.core.models import TenantScopedModel
from apps.orders.models.order_status import OrderStatus


class Order(TenantScopedModel):
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="orders"
    )
    cart = models.ForeignKey(
        "carts.Cart",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    order_number = models.BigIntegerField()  # Per-tenant monotonic, set via sequence
    status = models.CharField(
        max_length=16, choices=OrderStatus.choices, default=OrderStatus.PENDING
    )

    # Totals
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)

    # Address snapshots (deletions on Address don't affect orders)
    shipping_address = models.JSONField()
    billing_address = models.JSONField()

    # B2B fields
    is_b2b = models.BooleanField(default=False)
    tax_id = models.CharField(max_length=64, blank=True, default="")

    # PO / invoiced-payment snapshot (set when payment method is purchase_order).
    # `payment_terms` mirrors `PaymentMethod.payment_terms` (e.g. "net_30").
    # `po_number` is the customer's own reference; we don't generate it.
    # `payment_due_date` is computed at checkout from terms + now().
    payment_terms = models.CharField(max_length=16, blank=True, default="")
    po_number = models.CharField(max_length=64, blank=True, default="")
    payment_due_date = models.DateField(null=True, blank=True)

    # Idempotency
    idempotency_key = models.CharField(max_length=128, unique=True)

    Status = OrderStatus

    class Meta:
        db_table = "orders_order"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "order_number"],
                name="uniq_order_number_per_tenant",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "customer", "-created_at"],
                name="orders_orde_tenant_cust_idx",
            ),
            models.Index(fields=["tenant", "status"], name="orders_orde_tenant_status_idx"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.order_number} ({self.status})"
