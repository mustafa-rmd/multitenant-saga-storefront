"""
`version` is incremented on every mutation. Clients can opt-in to
optimistic locking with the If-Match header, but it's not required --
the cart row is SELECT FOR UPDATE'd on every mutation, so the
operations themselves are serialized.
"""

from django.db import models

from apps.carts.models.cart_status import CartStatus
from apps.core.models import TenantScopedModel


class Cart(TenantScopedModel):
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="carts"
    )
    status = models.CharField(max_length=16, choices=CartStatus.choices, default=CartStatus.ACTIVE)
    currency = models.CharField(max_length=3, blank=True, default="")
    version = models.IntegerField(default=0)

    # Cart slots: a single shipping address, billing address, payment method
    shipping_address = models.ForeignKey(
        "customers.Address",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    billing_address = models.ForeignKey(
        "customers.Address",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    selected_payment_method = models.ForeignKey(
        "payments.PaymentMethod",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    Status = CartStatus  # alias

    class Meta:
        db_table = "carts_cart"
        constraints = [
            # One active cart per customer. The partial unique constraint
            # allows multiple non-active carts (converted, abandoned)
            # while enforcing only one active at a time.
            models.UniqueConstraint(
                fields=["customer"],
                condition=models.Q(status="active"),
                name="one_active_cart_per_customer",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "customer", "status"], name="carts_cart_tenant__idx"),
            models.Index(
                fields=["tenant", "status", "updated_at"],
                name="carts_cart_tenant_status_idx",
            ),
        ]

    def __str__(self):
        return f"Cart {self.id} ({self.status})"
