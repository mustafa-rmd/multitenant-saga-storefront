from dataclasses import dataclass


@dataclass(frozen=True)
class GatewayCredentials:
    """Per-tenant credentials passed to a gateway at call time."""

    public_key: str | None = None
    secret_key: str | None = None
    webhook_secret: str | None = None
    extra: dict | None = None
