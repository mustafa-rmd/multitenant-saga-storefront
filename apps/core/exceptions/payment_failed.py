from apps.core.exceptions.domain_error import DomainError


class PaymentFailed(DomainError):
    code = "payment_failed"
    http_status = 402

    def __init__(self, detail=None, *, gateway_code=None):
        super().__init__(
            detail or "Payment failed",
            meta={"gateway_code": gateway_code} if gateway_code else None,
        )
