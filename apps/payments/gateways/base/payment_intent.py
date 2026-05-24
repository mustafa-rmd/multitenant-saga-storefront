from dataclasses import dataclass
from decimal import Decimal

from apps.payments.gateways.base.payment_status import PaymentStatus


@dataclass(frozen=True)
class PaymentIntent:
    """Normalized response from a gateway operation."""

    gateway_transaction_id: str
    status: PaymentStatus
    amount: Decimal
    currency: str
    next_action: dict | None = None
    raw_response: dict | None = None
