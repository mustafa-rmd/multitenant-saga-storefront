from apps.core.exceptions.domain_error import DomainError


class Forbidden(DomainError):
    code = "forbidden"
    http_status = 403
    detail = "You don't have access to this resource"
