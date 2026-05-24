from apps.core.exceptions.domain_error import DomainError


class InsufficientStock(DomainError):
    code = "insufficient_stock"
    http_status = 409

    def __init__(self, *, product_id=None, available=None, requested=None, items=None):
        if items:
            self.detail = "One or more items are out of stock"
            self.meta = {
                "items": [
                    {"product_id": str(pid), "available": av, "requested": rq}
                    for pid, av, rq in items
                ]
            }
        else:
            self.detail = f"Only {available} available, {requested} requested"
            self.meta = {
                "product_id": str(product_id),
                "available": available,
                "requested": requested,
            }
        super().__init__(self.detail, meta=self.meta)
