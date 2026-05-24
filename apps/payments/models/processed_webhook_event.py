"""
ProcessedWebhookEvent -- the dedupe ledger for inbound gateway webhooks.

Stripe (and most gateways) redeliver webhooks aggressively: any 5xx, any
timeout, any slow response causes a retry. Without a dedupe layer,
`process_webhook_event` runs twice for the same event and side effects
like `stock_quantity -= res.quantity` happen twice.

Pattern: INSERT a row keyed by `(gateway_name, event_id)` BEFORE mutating
anything. The UNIQUE constraint makes a duplicate fail with IntegrityError;
the task catches it and returns early. This is the standard idempotency
pattern recommended by Stripe's own integration docs.

Cross-tenant by design: the webhook handler runs without tenant context
(the tenant is resolved from the Payment record), and dedupe must be
global so a malicious tenant can't replay another tenant's events.
"""

import uuid

from django.db import models


class ProcessedWebhookEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gateway_name = models.CharField(max_length=32)
    event_id = models.CharField(max_length=255)
    event_type = models.CharField(max_length=64)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payments_processedwebhookevent"
        constraints = [
            models.UniqueConstraint(
                fields=["gateway_name", "event_id"],
                name="uniq_webhook_event_per_gateway",
            ),
        ]
        indexes = [
            # for janitor sweeps
            models.Index(fields=["processed_at"], name="payments_pr_proc_at_idx"),
        ]

    def __str__(self):
        return f"{self.gateway_name}:{self.event_id}"
