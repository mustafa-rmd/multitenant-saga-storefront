from apps.core.exceptions.domain_error import DomainError


class Unauthorized(DomainError):
    code = "unauthorized"
    http_status = 401
    detail = "Authentication required"
