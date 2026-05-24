"""
StripeGateway adapters.

Two registered classes share one implementation:

  * `StripeGateway` (name="stripe") — uses `STRIPE_API_BASE` env, which
    points at `stripe-mock` in dev. Useful for request-shape validation
    and CI without a real Stripe account.

  * `StripeLiveGateway` (name="stripe_live") — pins `api.stripe.com`,
    ignores the env. Use this for real test-mode (sk_test_*) or live
    (sk_live_*) credentials.

Why two classes: the Stripe SDK exposes `stripe.api_base` as a process-
global. To let both gateways coexist in a single Django/Celery process,
each adapter sets `stripe.api_base` to its instance value just before
every SDK call (`_configure_sdk`). Safe under sync workers because each
request runs serially within a process; threaded servers would need
per-request locking or the SDK's `StripeClient` class.

Skeletal in the same ways for both classes:

  - `tokenize()` raises NotImplementedError — real Stripe tokenization
    happens client-side via Stripe.js; the storefront passes us a token.
  - Webhook event-type mapping covers the common cases; production needs
    the full event taxonomy.
  - No `automatic_payment_methods` or saved-customer flows yet.

stripe-mock is stateless, so the `stripe` adapter validates request shape
(URLs, params, idempotency headers) but not actual payment outcomes —
use `stripe_live` against a real test-mode account to exercise full
state transitions and see them in dashboard.stripe.com.
"""

import logging
import os
from decimal import Decimal

import stripe as stripe_sdk

from apps.payments.gateways.base import (
    GatewayCapabilities,
    GatewayCredentials,
    PaymentGateway,
    PaymentIntent,
    PaymentStatus,
    TokenizedPaymentMethod,
    WebhookEvent,
)

log = logging.getLogger(__name__)


# Fallback when neither env nor class override is set. Matches Stripe SDK
# default; only here so we don't accidentally inherit a leftover api_base
# set by another adapter on the same process.
_STRIPE_DEFAULT_API_BASE = "https://api.stripe.com"


_STATUS_MAP = {
    "requires_payment_method": PaymentStatus.PENDING,
    "requires_action": PaymentStatus.PENDING,
    "requires_confirmation": PaymentStatus.PENDING,
    "processing": PaymentStatus.PENDING,
    "requires_capture": PaymentStatus.AUTHORIZED,
    "succeeded": PaymentStatus.CAPTURED,
    "canceled": PaymentStatus.CANCELLED,
}


_SUPPORTED_CURRENCIES = {
    "USD",
    "EUR",
    "GBP",
    "SAR",
    "AED",
    "JPY",
    "AUD",
    "CAD",
}


def _stripe_obj_to_dict(obj) -> dict:
    """Stripe SDK >=14 dropped `to_dict_recursive`. Use `to_dict` and recurse
    through nested StripeObjects so the result is JSON-serialisable."""
    raw = obj.to_dict() if hasattr(obj, "to_dict") else obj  # already a dict or scalar

    def _convert(value):
        if hasattr(value, "to_dict"):
            return _convert(value.to_dict())
        if isinstance(value, dict):
            return {k: _convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_convert(v) for v in value]
        return value

    return _convert(raw)


class StripeGateway(PaymentGateway):
    """Stripe adapter with env-driven api_base (default: STRIPE_API_BASE,
    pointing at stripe-mock in dev)."""

    name = "stripe"

    # Subclass-overridable. None → read STRIPE_API_BASE at call time.
    api_base: str | None = None

    def _resolve_api_base(self) -> str:
        if self.api_base:
            return self.api_base
        return os.environ.get("STRIPE_API_BASE") or _STRIPE_DEFAULT_API_BASE

    def _configure_sdk(self) -> None:
        """Pin the process-global SDK config to this instance's target.

        The Stripe SDK exposes `api_base` / `verify_ssl_certs` as module
        globals. With two gateways (stripe + stripe_live) sharing one
        process, we must re-set them before every call — otherwise the
        last gateway-instance wins for whoever runs second.
        """
        api_base = self._resolve_api_base()
        stripe_sdk.api_base = api_base
        stripe_sdk.upload_api_base = os.environ.get("STRIPE_UPLOAD_API_BASE", api_base)
        # stripe-mock is HTTP; real Stripe needs SSL verification on.
        stripe_sdk.verify_ssl_certs = api_base.startswith("https://")

    def supports_currency(self, currency: str) -> bool:
        return currency.upper() in _SUPPORTED_CURRENCIES

    def describe(self, *, credentials: GatewayCredentials) -> GatewayCapabilities:
        # `public_key` in the JSONB is Stripe's pk_test_xxx / pk_live_xxx.
        # Safe to send to the browser -- that's literally what it's for.
        # The secret_key + webhook_secret in the same record are deliberately
        # not in the output here.
        return GatewayCapabilities(
            supported_currencies=sorted(_SUPPORTED_CURRENCIES),
            tokenization="client",
            supports_3ds=True,
            public_credentials={"publishable_key": credentials.public_key or ""},
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
        self._configure_sdk()
        meta = metadata or {}

        # Lift order + customer fields out of metadata into the
        # PaymentIntent's first-class slots so the Stripe dashboard
        # shows them in the row preview (description) and customer
        # column (receipt_email). The metadata dict itself still flows
        # through verbatim — Stripe shows it in the side panel of each
        # PaymentIntent. The checkout saga populates these keys; older
        # call sites that don't ship them get a minimal description.
        order_num = meta.get("order_number")
        cust_name = meta.get("customer_name")
        cust_email = meta.get("customer_email")
        if order_num and cust_name:
            description = f"Order #{order_num} — {cust_name}"
        elif order_num:
            description = f"Order #{order_num}"
        elif cust_name:
            description = cust_name
        else:
            description = None

        kwargs: dict = {
            "amount": int(amount * 100),
            "currency": currency.lower(),
            "payment_method": payment_method_token,
            "confirm": True,
            "capture_method": "manual",  # we capture in a second step
            # Restrict to non-redirect payment methods. Stripe accounts
            # enable a broad set by default (Klarna, iDEAL, etc.) that
            # would demand a `return_url` the storefront isn't wired to
            # handle. Opting redirects off keeps the saga sync-friendly
            # without requiring per-account dashboard tweaks.
            "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
            "metadata": meta,
            "api_key": credentials.secret_key,
            "idempotency_key": idempotency_key,
        }
        if description:
            kwargs["description"] = description
        if cust_email:
            kwargs["receipt_email"] = cust_email

        intent = stripe_sdk.PaymentIntent.create(**kwargs)
        return PaymentIntent(
            gateway_transaction_id=intent.id,
            status=_STATUS_MAP.get(intent.status, PaymentStatus.PENDING),
            amount=Decimal(intent.amount) / 100,
            currency=intent.currency.upper(),
            next_action=self._extract_next_action(intent),
            raw_response=_stripe_obj_to_dict(intent),
        )

    def capture(
        self,
        *,
        credentials: GatewayCredentials,
        gateway_transaction_id: str,
        idempotency_key: str,
        amount: Decimal | None = None,
    ) -> PaymentIntent:
        self._configure_sdk()
        kwargs = {
            "api_key": credentials.secret_key,
            "idempotency_key": idempotency_key,
        }
        if amount is not None:
            kwargs["amount_to_capture"] = int(amount * 100)

        intent = stripe_sdk.PaymentIntent.capture(gateway_transaction_id, **kwargs)
        return PaymentIntent(
            gateway_transaction_id=intent.id,
            status=_STATUS_MAP.get(intent.status, PaymentStatus.FAILED),
            amount=Decimal(intent.amount_received) / 100,
            currency=intent.currency.upper(),
            raw_response=_stripe_obj_to_dict(intent),
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
        self._configure_sdk()
        kwargs = {
            "payment_intent": gateway_transaction_id,
            "api_key": credentials.secret_key,
            "idempotency_key": idempotency_key,
        }
        if amount is not None:
            kwargs["amount"] = int(amount * 100)
        if reason:
            kwargs["reason"] = reason
        refund = stripe_sdk.Refund.create(**kwargs)
        return PaymentIntent(
            gateway_transaction_id=gateway_transaction_id,
            status=PaymentStatus.REFUNDED,
            amount=Decimal(refund.amount) / 100,
            currency=refund.currency.upper(),
            raw_response=_stripe_obj_to_dict(refund),
        )

    def retrieve_payment(
        self,
        *,
        credentials: GatewayCredentials,
        gateway_transaction_id: str,
    ) -> PaymentIntent | None:
        self._configure_sdk()
        try:
            intent = stripe_sdk.PaymentIntent.retrieve(
                gateway_transaction_id,
                api_key=credentials.secret_key,
            )
        except stripe_sdk.error.InvalidRequestError:
            # Intent not found (e.g. wrong id, or it never existed).
            return None
        return PaymentIntent(
            gateway_transaction_id=intent.id,
            status=_STATUS_MAP.get(intent.status, PaymentStatus.PENDING),
            amount=Decimal(intent.amount) / 100,
            currency=intent.currency.upper(),
            next_action=self._extract_next_action(intent),
            raw_response=_stripe_obj_to_dict(intent),
        )

    def tokenize(
        self,
        *,
        credentials: GatewayCredentials,
        payload: dict,
    ) -> TokenizedPaymentMethod:
        raise NotImplementedError(
            "Stripe tokenization happens client-side via Stripe.js. "
            "Pass an existing pm_xxx token to the PaymentMethod constructor."
        )

    def verify_webhook(
        self,
        *,
        credentials: GatewayCredentials,
        raw_body: bytes,
        signature_header: str,
    ) -> bool:
        try:
            stripe_sdk.Webhook.construct_event(
                payload=raw_body,
                sig_header=signature_header,
                secret=credentials.webhook_secret,
            )
            return True
        except stripe_sdk.error.SignatureVerificationError as e:
            log.warning("Stripe webhook signature verification failed: %s", e)
            return False

    def parse_webhook(
        self,
        *,
        raw_body: bytes,
    ) -> WebhookEvent:
        import json

        event = json.loads(raw_body)
        obj = event["data"]["object"]
        normalized_type = self._normalize_event_type(event["type"])

        # For charge.* events the inner object is a Charge whose `id` is
        # `ch_…`, but `Payment.gateway_transaction_id` stores the parent
        # PaymentIntent id (`pi_…`). Without this branch refund webhooks
        # 404 in the lookup step.
        if obj.get("object") == "charge":
            gateway_txn_id = obj.get("payment_intent") or obj["id"]
            # A refunded Charge still has status="succeeded"; use the
            # normalized event type to decide the payment-side status.
            if normalized_type == "payment.refunded":
                status = PaymentStatus.REFUNDED
            else:
                status = _STATUS_MAP.get(obj.get("status"), PaymentStatus.PENDING)
        else:
            gateway_txn_id = obj["id"]
            status = _STATUS_MAP.get(obj.get("status"), PaymentStatus.PENDING)

        return WebhookEvent(
            event_type=normalized_type,
            event_id=event["id"],  # Stripe's evt_xxx -- stable across redeliveries
            gateway_transaction_id=gateway_txn_id,
            status=status,
            raw_payload=event,
        )

    @staticmethod
    def _extract_next_action(intent) -> dict | None:
        if intent.status == "requires_action" and intent.next_action:
            na = intent.next_action
            url = None
            if hasattr(na, "redirect_to_url") and na.redirect_to_url:
                url = (
                    na.redirect_to_url.get("url")
                    if isinstance(na.redirect_to_url, dict)
                    else na.redirect_to_url.url
                )
            return {"type": na.type, "url": url}
        return None

    @staticmethod
    def _normalize_event_type(stripe_type: str) -> str:
        return {
            "payment_intent.succeeded": "payment.captured",
            "payment_intent.payment_failed": "payment.failed",
            "payment_intent.canceled": "payment.cancelled",
            "charge.refunded": "payment.refunded",
        }.get(stripe_type, "payment.unknown")


class StripeLiveGateway(StripeGateway):
    """Stripe adapter pinned to api.stripe.com.

    Identical behaviour to `StripeGateway` except the SDK target is
    always real Stripe — ignores STRIPE_API_BASE so the mock-pointed
    `stripe` adapter can coexist in the same process. Use with
    sk_test_* (sandbox) or sk_live_* (production) credentials stored
    on the tenant's PaymentGatewayConfig row.
    """

    name = "stripe_live"
    api_base = _STRIPE_DEFAULT_API_BASE
