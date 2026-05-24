from django.db import models

from apps.core.models import TenantScopedModel
from apps.orders.models.order import Order


class Invoice(TenantScopedModel):
    """Bonus: invoice for an order. PDF generation is async via Celery."""

    order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="invoice")
    invoice_number = models.BigIntegerField()
    pdf_url = models.URLField(blank=True, default="")
    issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "orders_invoice"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "invoice_number"],
                name="uniq_invoice_number_per_tenant",
            ),
        ]
