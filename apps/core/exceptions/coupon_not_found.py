from apps.core.exceptions.resource_not_found import ResourceNotFound


class CouponNotFound(ResourceNotFound):
    code = "coupon_not_found"
