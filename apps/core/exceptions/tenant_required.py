from apps.core.exceptions.domain_error import DomainError


class TenantRequired(DomainError):
    code = "tenant_required"
    http_status = 400
    detail = "A tenant subdomain is required"
