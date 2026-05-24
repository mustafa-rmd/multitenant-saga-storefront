from enum import StrEnum


class PaymentStatus(StrEnum):
    """Gateway-normalized payment statuses. Map to Payment.Status on persist."""

    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"
