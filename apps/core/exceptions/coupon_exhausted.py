from apps.core.exceptions.domain_error import DomainError


class CouponExhausted(DomainError):
    code = "coupon_exhausted"
    http_status = 409
