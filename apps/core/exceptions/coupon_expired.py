from apps.core.exceptions.domain_error import DomainError


class CouponExpired(DomainError):
    code = "coupon_expired"
    http_status = 410
