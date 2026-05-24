from apps.core.exceptions.domain_error import DomainError


class GatewayNotConfigured(DomainError):
    code = "gateway_not_configured"
    http_status = 409
