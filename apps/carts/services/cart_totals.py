from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class CartTotals:
    subtotal: Decimal
    discount_total: Decimal
    grand_total: Decimal
    currency: str
