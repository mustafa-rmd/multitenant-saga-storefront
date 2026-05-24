from apps.core.exceptions.domain_error import DomainError


class CouponInvalid(DomainError):
    code = "coupon_invalid"
    http_status = 409
