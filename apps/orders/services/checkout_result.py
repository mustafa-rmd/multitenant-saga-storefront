from dataclasses import dataclass

from apps.orders.models import Order


@dataclass(frozen=True)
class CheckoutResult:
    order: Order
    payment_status: str
    next_action: dict | None = None
