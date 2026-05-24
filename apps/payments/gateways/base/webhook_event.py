from dataclasses import dataclass

from apps.payments.gateways.base.payment_status import PaymentStatus


@dataclass(frozen=True)
class WebhookEvent:
    """Normalized representation of a gateway webhook.

    `event_id` is the gateway's own event identifier (Stripe's `evt_...`,
    HyperPay's `id`, etc.) and is used by the dedupe table to refuse
    duplicate deliveries. Every gateway's `parse_webhook` MUST populate it.
    """

    event_type: str  # our normalized event names
    event_id: str  # gateway-native event id (for dedupe)
    gateway_transaction_id: str
    status: PaymentStatus
    raw_payload: dict
