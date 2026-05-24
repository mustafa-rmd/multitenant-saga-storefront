"""
Coupon model with pluggable constraints.

Constraints supported:
- min_cart_subtotal (Decimal)
- allowed_countries (list of ISO 3166-1 alpha-2 codes; empty = all)
- customer_type_restriction (B2C, B2B, or both)
- max_uses (total uses across all customers)
- valid_from / valid_until

`uses_count` is incremented atomically at order creation time. The Coupon
table row is locked during that increment to prevent overshooting max_uses
under concurrent checkouts.
"""

from apps.coupons.models.coupon import Coupon
from apps.coupons.models.customer_type_restriction import CustomerTypeRestriction
from apps.coupons.models.discount_type import DiscountType

__all__ = ["DiscountType", "CustomerTypeRestriction", "Coupon"]
