from apps.core.exceptions.domain_error import DomainError


class GatewayUnsupportedCurrency(DomainError):
    code = "gateway_unsupported_currency"
    http_status = 409

    def __init__(self, *, gateway, currency):
        super().__init__(
            f"Gateway {gateway} does not support currency {currency}",
            meta={"gateway": gateway, "currency": currency},
        )
