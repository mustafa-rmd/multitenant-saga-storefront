from apps.core.exceptions.domain_error import DomainError


class OrderNotCancellable(DomainError):
    """Raised when a cancel request hits an order whose status doesn't
    permit cancellation (only `pending` orders are cancellable; once
    captured / fulfilled the refund path applies instead)."""

    code = "order_not_cancellable"
    http_status = 409
    detail = "This order can no longer be cancelled"
