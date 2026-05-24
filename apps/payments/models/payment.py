from django.db import models

from apps.core.models import TenantScopedModel
from apps.payments.models.payment_gateway_config import PaymentGatewayConfig
from apps.payments.models.payment_status import PaymentStatus


class Payment(TenantScopedModel):
    """An attempt to take money against an order."""

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    gateway_config = models.ForeignKey(
        PaymentGatewayConfig,
        on_delete=models.PROTECT,
        related_name="payments",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=16, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    gateway_transaction_id = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=128, unique=True)
    gateway_response = models.JSONField(default=dict, blank=True)

    Status = PaymentStatus  # alias for ergonomic access

    class Meta:
        db_table = "payments_payment"
        indexes = [
            models.Index(fields=["gateway_transaction_id"], name="payments_pa_gateway_idx"),
            models.Index(fields=["order", "status"], name="payments_pa_order_status_idx"),
            models.Index(fields=["tenant", "status"], name="payments_pa_tenant_status_idx"),
        ]

    def __str__(self):
        return f"Payment {self.id} -- {self.status}"
