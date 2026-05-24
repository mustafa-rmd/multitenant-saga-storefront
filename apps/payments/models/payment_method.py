from django.db import models

from apps.core.models import TenantScopedModel
from apps.payments.models.payment_gateway_config import PaymentGatewayConfig
from apps.payments.models.payment_method_type import PaymentMethodType


class PaymentMethod(TenantScopedModel):
    """A customer's saved payment instrument.

    Two variants share this table:

      * `method_type=card` — tokenized via a PaymentGatewayConfig. The cart's
        checkout path calls the gateway's authorize/capture.
      * `method_type=purchase_order` — B2B invoiced payment. No gateway, no
        token. The order is created in PENDING (awaiting invoice payment),
        stock is committed immediately, and a tenant admin flips it to PAID
        via `POST /admin/orders/{id}/mark-paid` when the wire/cheque clears.
    """

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="payment_methods"
    )
    method_type = models.CharField(
        max_length=16,
        choices=PaymentMethodType.choices,
        default=PaymentMethodType.CARD,
    )
    gateway_config = models.ForeignKey(
        PaymentGatewayConfig,
        on_delete=models.PROTECT,
        related_name="payment_methods",
        null=True,
        blank=True,
    )
    token = models.CharField(max_length=255, blank=True, default="")
    brand = models.CharField(max_length=32, blank=True)  # visa, mada, mastercard
    last_four = models.CharField(max_length=4, blank=True)
    # PO-only display label, e.g. "Acme Corp net-30"
    po_account_label = models.CharField(max_length=128, blank=True, default="")
    # PO-only payment terms snapshot, e.g. "net_30"
    payment_terms = models.CharField(max_length=16, blank=True, default="")
    is_default = models.BooleanField(default=False)

    Type = PaymentMethodType  # alias for ergonomic access

    class Meta:
        db_table = "payments_paymentmethod"
        constraints = [
            models.UniqueConstraint(
                fields=["customer"],
                condition=models.Q(is_default=True),
                name="one_default_method_per_customer",
            ),
            # Card methods MUST have a gateway_config; PO methods MUST NOT.
            models.CheckConstraint(
                check=(
                    models.Q(method_type="card", gateway_config__isnull=False)
                    | models.Q(method_type="purchase_order", gateway_config__isnull=True)
                ),
                name="paymentmethod_gateway_matches_type",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "customer"], name="payments_pa_tenant__idx"),
        ]

    def __str__(self):
        if self.method_type == PaymentMethodType.PURCHASE_ORDER:
            return f"PO: {self.po_account_label or 'unnamed'}"
        return f"{self.brand} ****{self.last_four}"
