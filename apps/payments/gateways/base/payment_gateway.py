from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from apps.payments.gateways.base.gateway_capabilities import GatewayCapabilities
from apps.payments.gateways.base.gateway_credentials import GatewayCredentials
from apps.payments.gateways.base.payment_intent import PaymentIntent
from apps.payments.gateways.base.tokenized_payment_method import TokenizedPaymentMethod
from apps.payments.gateways.base.webhook_event import WebhookEvent


class PaymentGateway(ABC):
    """Every gateway implements this interface."""

    name: str = ""  # subclasses must set

    @abstractmethod
    def authorize(
        self,
        *,
        credentials: GatewayCredentials,
        amount: Decimal,
        currency: str,
        payment_method_token: str,
        idempotency_key: str,
        metadata: dict | None = None,
    ) -> PaymentIntent:
        """Reserve funds. May return PENDING (needs user action) or AUTHORIZED."""

    @abstractmethod
    def capture(
        self,
        *,
        credentials: GatewayCredentials,
        gateway_transaction_id: str,
        idempotency_key: str,
        amount: Decimal | None = None,
    ) -> PaymentIntent:
        """Move authorized funds to our account."""

    @abstractmethod
    def refund(
        self,
        *,
        credentials: GatewayCredentials,
        gateway_transaction_id: str,
        idempotency_key: str,
        amount: Decimal | None = None,
        reason: str | None = None,
    ) -> PaymentIntent:
        """Refund a captured payment, fully or partially."""

    @abstractmethod
    def retrieve_payment(
        self,
        *,
        credentials: GatewayCredentials,
        gateway_transaction_id: str,
    ) -> PaymentIntent | None:
        """Ask the gateway for the current state of a known payment.

        Used by the reconciliation sweep to converge Payment rows stuck
        in PENDING: if the gateway says the intent succeeded but we never
        recorded the result, we move the row forward. Returns None if the
        gateway can't find the intent (e.g. it never existed).
        """

    @abstractmethod
    def tokenize(
        self,
        *,
        credentials: GatewayCredentials,
        payload: dict,
    ) -> TokenizedPaymentMethod:
        """Convert raw card data into a persistent token. Most production
        gateways do this client-side; this exists for the mock + any
        future gateway that needs server-side tokenization."""

    @abstractmethod
    def verify_webhook(
        self,
        *,
        credentials: GatewayCredentials,
        raw_body: bytes,
        signature_header: str,
    ) -> bool:
        """Validate webhook signature."""

    @abstractmethod
    def parse_webhook(
        self,
        *,
        raw_body: bytes,
    ) -> WebhookEvent:
        """Translate gateway-specific webhook payload to our normalized form."""

    def supports_currency(self, currency: str) -> bool:
        """Override to declare currency support. Default: accept all."""
        return True

    def describe(self, *, credentials: GatewayCredentials) -> GatewayCapabilities:
        """Return what this gateway can do for `credentials`.

        Surfaces through `GET /payment-gateways/{name}` so a storefront
        can render the right form / pick the right SDK. The default is
        intentionally conservative — concrete gateways override.
        """
        return GatewayCapabilities(
            supported_currencies=[],
            tokenization="server",
            supports_3ds=False,
            public_credentials={},
        )
