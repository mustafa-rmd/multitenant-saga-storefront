"""Module-level registry of payment gateways. Stateless lookup by name."""

from apps.payments.gateways.base import PaymentGateway

_REGISTRY: dict[str, type[PaymentGateway]] = {}


def register(gateway_class: type[PaymentGateway]) -> None:
    if not gateway_class.name:
        raise ValueError(f"{gateway_class} must set a `name` class attribute")
    if gateway_class.name in _REGISTRY:
        # Re-registering with the same class is fine (idempotent on import)
        if _REGISTRY[gateway_class.name] is gateway_class:
            return
        raise ValueError(f"Gateway '{gateway_class.name}' already registered")
    _REGISTRY[gateway_class.name] = gateway_class


def get(name: str) -> PaymentGateway:
    if name not in _REGISTRY:
        raise ValueError(f"Unknown payment gateway '{name}'. Available: {list(_REGISTRY)}")
    return _REGISTRY[name]()


def available() -> list[str]:
    return list(_REGISTRY)
