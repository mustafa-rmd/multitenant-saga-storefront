from django.db import models


class GatewayName(models.TextChoices):
    MOCK = "mock", "Mock (test gateway)"
    # Stripe via stripe-mock or whatever STRIPE_API_BASE env points at.
    # Default in dev: http://stripe-mock:12111 (request-shape testing only).
    STRIPE = "stripe", "Stripe (env-configured api_base)"
    # Stripe pinned to api.stripe.com — real sandbox or live keys.
    # Ignores STRIPE_API_BASE so both adapters can coexist in one process.
    STRIPE_LIVE = "stripe_live", "Stripe (live api.stripe.com)"
    HYPERPAY = "hyperpay", "HyperPay"
    TAP = "tap", "Tap"
