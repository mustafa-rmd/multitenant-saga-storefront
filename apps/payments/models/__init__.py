"""
Payment models.

PaymentGatewayConfig: per-tenant configuration for a gateway. Each tenant
can have multiple configs (e.g. Stripe for international, HyperPay for
regional) with one default.

PaymentMethod: a customer's tokenized payment instrument. We never store
raw card data -- only the gateway-issued token. This keeps us out of PCI
scope.

Payment: an attempt to take money against an Order. The idempotency_key
is unique -- two requests with the same key cannot produce two Payment
rows. Combined with gateway-level idempotency keys, this makes "outage
= money lost" not happen.
"""

from apps.payments.models.gateway_name import GatewayName
from apps.payments.models.payment import Payment
from apps.payments.models.payment_gateway_config import PaymentGatewayConfig
from apps.payments.models.payment_method import PaymentMethod
from apps.payments.models.payment_method_type import PaymentMethodType
from apps.payments.models.processed_webhook_event import ProcessedWebhookEvent

# Note: the model-level PaymentStatus enum is exposed as Payment.Status.
# A second `PaymentStatus` exists under apps.payments.gateways.base for
# the gateway-normalized state; don't conflate them.

__all__ = [
    "GatewayName",
    "PaymentGatewayConfig",
    "PaymentMethod",
    "PaymentMethodType",
    "Payment",
    "ProcessedWebhookEvent",
]
