from apps.core.exceptions.domain_error import DomainError


class CartVersionConflict(DomainError):
    code = "cart_version_conflict"
    http_status = 409

    def __init__(self, *, expected, actual):
        super().__init__(
            "Cart was modified since you last read it. Refresh and retry.",
            meta={"expected": expected, "actual": actual},
        )
