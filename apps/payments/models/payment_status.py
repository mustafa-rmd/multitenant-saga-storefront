from django.db import models


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"  # created, not yet acted on
    INVOICE_PENDING = "invoice_pending", "Invoice Pending"  # PO: awaiting invoice payment
    AUTHORIZED = "authorized", "Authorized"  # funds held
    CAPTURED = "captured", "Captured"  # funds taken
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"
    CANCELLED = "cancelled", "Cancelled"
