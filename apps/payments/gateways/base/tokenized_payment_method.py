from dataclasses import dataclass


@dataclass(frozen=True)
class TokenizedPaymentMethod:
    gateway_token: str
    brand: str
    last_four: str
    raw_response: dict | None = None
