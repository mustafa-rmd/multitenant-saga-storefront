from apps.core.exceptions.domain_error import DomainError


class TenantNotFound(DomainError):
    code = "tenant_not_found"
    http_status = 404
    detail = "Tenant subdomain does not resolve to an active tenant"
