"""
MockPaymentGateway -- always-succeeds (or controllable-failure) gateway
for tests and local dev.

This is NOT just a test mock; it's a real implementation of the gateway
interface. Outcome can be controlled via the metadata dict:

    metadata={"mock_outcome": "decline"}            -> FAILED
    metadata={"mock_outcome": "requires_action"}    -> PENDING with redirect
    metadata={"mock_outcome": "success"}            -> AUTHORIZED (default)
"""

import hashlib
import json
import uuid
from decimal import Decimal

from apps.payments.gateways.base import (
    GatewayCapabilities,
    GatewayCredentials,
    PaymentGateway,
    PaymentIntent,
    PaymentStatus,
    TokenizedPaymentMethod,
    WebhookEvent,
)


class MockPaymentGateway(PaymentGateway):
    name = "mock"

    def describe(self, *, credentials: GatewayCredentials) -> GatewayCapabilities:
        # Empty supported_currencies means "accept everything" -- matches
        # the default `supports_currency()` behaviour. Server-side tokenize
        # because the test/dev flow needs to mint tokens without a browser
        # SDK. 3DS is supported via metadata={"mock_outcome": "requires_action"}.
        return GatewayCapabilities(
            supported_currencies=[],
            tokenization="server",
            supports_3ds=True,
            public_credentials={},
        )

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
        outcome = (metadata or {}).get("mock_outcome", "success")
        txn_id = f"mock_txn_{uuid.uuid4()}"

        if outcome == "decline":
            return PaymentIntent(
                gateway_transaction_id=txn_id,
                status=PaymentStatus.FAILED,
                amount=amount,
                currency=currency,
                raw_response={
                    "mock": True,
                    "outcome": "declined",
                    "failure_code": "card_declined",
                    "failure_message": "Mock decline",
                },
            )

        if outcome == "requires_action":
            return PaymentIntent(
                gateway_transaction_id=txn_id,
                status=PaymentStatus.PENDING,
                amount=amount,
                currency=currency,
                next_action={
                    "type": "redirect",
                    "url": "https://mock.gateway.local/3ds-challenge",
                },
                raw_response={"mock": True, "outcome": "requires_action"},
            )

        return PaymentIntent(
            gateway_transaction_id=txn_id,
            status=PaymentStatus.AUTHORIZED,
            amount=amount,
            currency=currency,
            raw_response={"mock": True, "outcome": "authorized"},
        )

    def capture(
        self,
        *,
        credentials: GatewayCredentials,
        gateway_transaction_id: str,
        idempotency_key: str,
        amount: Decimal | None = None,
    ) -> PaymentIntent:
        return PaymentIntent(
            gateway_transaction_id=gateway_transaction_id,
            status=PaymentStatus.CAPTURED,
            amount=amount or Decimal("0"),
            currency="SAR",
            raw_response={"mock": True, "outcome": "captured"},
        )

    def refund(
        self,
        *,
        credentials: GatewayCredentials,
        gateway_transaction_id: str,
        idempotency_key: str,
        amount: Decimal | None = None,
        reason: str | None = None,
    ) -> PaymentIntent:
        return PaymentIntent(
            gateway_transaction_id=gateway_transaction_id,
            status=PaymentStatus.REFUNDED,
            amount=amount or Decimal("0"),
            currency="SAR",
            raw_response={"mock": True, "outcome": "refunded", "reason": reason},
        )

    def retrieve_payment(
        self,
        *,
        credentials: GatewayCredentials,
        gateway_transaction_id: str,
    ) -> PaymentIntent | None:
        """Mock retrieval: any well-formed mock_txn_* id resolves to AUTHORIZED.

        Real gateways look up the intent in their database; the mock has no
        such store, so it returns a deterministic "authorized" result that
        lets reconciliation tests converge a stuck PENDING row.
        """
        if not gateway_transaction_id or not gateway_transaction_id.startswith("mock_txn_"):
            return None
        return PaymentIntent(
            gateway_transaction_id=gateway_transaction_id,
            status=PaymentStatus.AUTHORIZED,
            amount=Decimal("0"),
            currency="SAR",
            raw_response={"mock": True, "outcome": "retrieved", "status": "authorized"},
        )

    def tokenize(
        self,
        *,
        credentials: GatewayCredentials,
        payload: dict,
    ) -> TokenizedPaymentMethod:
        return TokenizedPaymentMethod(
            gateway_token=f"tok_mock_{uuid.uuid4()}",
            brand=payload.get("brand", "visa"),
            last_four=payload.get("last_four", "4242"),
            raw_response={"mock": True},
        )

    def verify_webhook(
        self,
        *,
        credentials: GatewayCredentials,
        raw_body: bytes,
        signature_header: str,
    ) -> bool:
        # Mock accepts a fixed signature
        return signature_header == "mock-signature"

    def parse_webhook(
        self,
        *,
        raw_body: bytes,
    ) -> WebhookEvent:
        payload = json.loads(raw_body)
        # event_id is required for dedupe. The mock gateway expects callers
        # to supply one; if missing, derive a deterministic id from the
        # payload so retries with the same body still dedupe correctly.
        # `hashlib` not `hash()` — the builtin is PYTHONHASHSEED-randomized
        # per process, which would defeat dedupe across worker restarts.
        event_id = (
            payload.get("event_id") or f"mock_evt_{hashlib.sha256(raw_body).hexdigest()[:16]}"
        )
        return WebhookEvent(
            event_type=payload["event_type"],
            event_id=event_id,
            gateway_transaction_id=payload["transaction_id"],
            status=PaymentStatus(payload["status"]),
            raw_payload=payload,
        )
