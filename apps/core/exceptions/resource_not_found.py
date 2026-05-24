from apps.core.exceptions.domain_error import DomainError


class ResourceNotFound(DomainError):
    code = "not_found"
    http_status = 404
