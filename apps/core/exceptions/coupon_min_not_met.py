from apps.core.exceptions.domain_error import DomainError


class CouponMinNotMet(DomainError):
    code = "coupon_min_not_met"
    http_status = 409

    def __init__(self, *, required, current):
        super().__init__(
            f"Cart subtotal {current} is below required minimum {required}",
            meta={"required": str(required), "current": str(current)},
        )
