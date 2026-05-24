from apps.payments.gateways.mock import MockPaymentGateway
from apps.payments.gateways.registry import available, get, register
from apps.payments.gateways.stripe import StripeGateway, StripeLiveGateway

# Register built-in gateways
register(MockPaymentGateway)
register(StripeGateway)
register(StripeLiveGateway)

__all__ = ["register", "get", "available"]
