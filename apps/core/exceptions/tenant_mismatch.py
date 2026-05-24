from apps.core.exceptions.domain_error import DomainError


class TenantMismatch(DomainError):
    code = "tenant_mismatch"
    http_status = 403
    detail = "Token tenant claim does not match the requested tenant"
