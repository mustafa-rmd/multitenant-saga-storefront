from django.db import models

from apps.core.models import TenantScopedModel
from apps.payments.models.gateway_name import GatewayName


class PaymentGatewayConfig(TenantScopedModel):
    """Per-tenant gateway credentials and config."""

    gateway_name = models.CharField(max_length=32, choices=GatewayName.choices)
    # TODO: encrypt at rest using KMS / Django's signing keys.
    # For the POC this is plaintext JSONB.
    credentials = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "payments_paymentgatewayconfig"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "gateway_name"],
                name="uniq_gateway_per_tenant",
            ),
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(is_default=True),
                name="one_default_gateway_per_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.gateway_name} for tenant {self.tenant_id}"
