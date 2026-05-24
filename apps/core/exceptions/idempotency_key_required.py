from apps.core.exceptions.domain_error import DomainError


class IdempotencyKeyRequired(DomainError):
    code = "idempotency_key_required"
    http_status = 400
    detail = "Idempotency-Key header is required"
