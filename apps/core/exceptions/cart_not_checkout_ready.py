from apps.core.exceptions.domain_error import DomainError


class CartNotCheckoutReady(DomainError):
    code = "cart_not_checkout_ready"
    http_status = 409
