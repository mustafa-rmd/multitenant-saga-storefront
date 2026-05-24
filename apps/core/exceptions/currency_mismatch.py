from apps.core.exceptions.domain_error import DomainError


class CurrencyMismatch(DomainError):
    code = "currency_mismatch"
    http_status = 409

    def __init__(self, *, cart_currency, product_currency):
        super().__init__(
            f"Cart currency is {cart_currency}, product is {product_currency}",
            meta={"cart_currency": cart_currency, "product_currency": product_currency},
        )
