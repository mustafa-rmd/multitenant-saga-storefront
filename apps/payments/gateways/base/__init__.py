"""
Abstract payment gateway interface.

Gateways are stateless. Per-tenant configuration is passed via a
GatewayCredentials object on every call. The cart/order code never
sees gateway-specific objects -- only normalized PaymentIntent and
WebhookEvent dataclasses.

This is the seam that makes the system pluggable. Adding a new gateway
is one new file + one register() call.
"""

from apps.payments.gateways.base.gateway_capabilities import GatewayCapabilities
from apps.payments.gateways.base.gateway_credentials import GatewayCredentials
from apps.payments.gateways.base.payment_gateway import PaymentGateway
from apps.payments.gateways.base.payment_intent import PaymentIntent
from apps.payments.gateways.base.payment_status import PaymentStatus
from apps.payments.gateways.base.tokenized_payment_method import TokenizedPaymentMethod
from apps.payments.gateways.base.webhook_event import WebhookEvent

__all__ = [
    "PaymentStatus",
    "PaymentIntent",
    "TokenizedPaymentMethod",
    "WebhookEvent",
    "GatewayCredentials",
    "GatewayCapabilities",
    "PaymentGateway",
]
