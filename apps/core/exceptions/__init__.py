"""
Domain-level exceptions. Raised by services, caught by the custom DRF
exception handler, and translated into our error envelope.

Keeping exceptions framework-agnostic means services can be called from
Celery, management commands, or future non-HTTP entry points without
coupling business logic to DRF.
"""

# Customer profile resources
from apps.core.exceptions.address_not_found import AddressNotFound

# Cart / checkout state
from apps.core.exceptions.cart_not_checkout_ready import CartNotCheckoutReady
from apps.core.exceptions.cart_not_found import CartNotFound
from apps.core.exceptions.cart_version_conflict import CartVersionConflict
from apps.core.exceptions.coupon_already_applied import CouponAlreadyApplied
from apps.core.exceptions.coupon_country_restricted import CouponCountryRestricted
from apps.core.exceptions.coupon_exhausted import CouponExhausted
from apps.core.exceptions.coupon_expired import CouponExpired

# Coupons
from apps.core.exceptions.coupon_invalid import CouponInvalid
from apps.core.exceptions.coupon_min_not_met import CouponMinNotMet
from apps.core.exceptions.coupon_not_found import CouponNotFound
from apps.core.exceptions.currency_mismatch import CurrencyMismatch
from apps.core.exceptions.customer_not_found import CustomerNotFound
from apps.core.exceptions.domain_error import DomainError
from apps.core.exceptions.forbidden import Forbidden
from apps.core.exceptions.gateway_not_configured import GatewayNotConfigured
from apps.core.exceptions.gateway_unsupported_currency import GatewayUnsupportedCurrency

# DRF exception handler
from apps.core.exceptions.handler import custom_exception_handler
from apps.core.exceptions.idempotency_key_required import IdempotencyKeyRequired
from apps.core.exceptions.insufficient_stock import InsufficientStock

# Orders
from apps.core.exceptions.order_not_cancellable import OrderNotCancellable

# Payments
from apps.core.exceptions.payment_failed import PaymentFailed
from apps.core.exceptions.payment_method_not_found import PaymentMethodNotFound
from apps.core.exceptions.product_not_found import ProductNotFound

# Resource not found
from apps.core.exceptions.resource_not_found import ResourceNotFound
from apps.core.exceptions.tenant_mismatch import TenantMismatch
from apps.core.exceptions.tenant_not_found import TenantNotFound

# Auth / tenant
from apps.core.exceptions.tenant_required import TenantRequired
from apps.core.exceptions.unauthorized import Unauthorized

__all__ = [
    "DomainError",
    "TenantRequired",
    "TenantNotFound",
    "Unauthorized",
    "Forbidden",
    "TenantMismatch",
    "ResourceNotFound",
    "AddressNotFound",
    "CartNotFound",
    "ProductNotFound",
    "PaymentMethodNotFound",
    "CouponNotFound",
    "CustomerNotFound",
    "CartNotCheckoutReady",
    "InsufficientStock",
    "CurrencyMismatch",
    "CartVersionConflict",
    "CouponInvalid",
    "CouponAlreadyApplied",
    "CouponMinNotMet",
    "CouponExpired",
    "CouponCountryRestricted",
    "CouponExhausted",
    "PaymentFailed",
    "GatewayUnsupportedCurrency",
    "GatewayNotConfigured",
    "IdempotencyKeyRequired",
    "OrderNotCancellable",
    "custom_exception_handler",
]
