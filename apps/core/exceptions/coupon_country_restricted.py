from apps.core.exceptions.domain_error import DomainError


class CouponCountryRestricted(DomainError):
    code = "coupon_country_restricted"
    http_status = 409
