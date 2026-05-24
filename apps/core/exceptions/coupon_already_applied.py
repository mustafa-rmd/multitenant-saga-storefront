from apps.core.exceptions.domain_error import DomainError


class CouponAlreadyApplied(DomainError):
    code = "coupon_already_applied"
    http_status = 409
