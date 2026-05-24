"""
Public, storefront-safe description of what a gateway can do.

Returned by `PaymentGateway.describe(credentials=...)`. The detail
endpoint at `GET /payment-gateways/{name}` serializes this so a
storefront frontend can pick the right SDK + render the right form
without hardcoding per-gateway knowledge or hitting an admin endpoint.

Nothing in here is a secret — `public_credentials` is for keys that
gateways explicitly designate as client-safe (e.g. Stripe's
`publishable_key`). Anything sensitive (secret_key, webhook_secret)
must never appear here.
"""

from dataclasses import dataclass, field
from typing import Literal

Tokenization = Literal["client", "server"]


@dataclass(frozen=True)
class GatewayCapabilities:
    """What a configured gateway is able to do.

    `supported_currencies` is the explicit allow-list a storefront uses
    to gate options against the cart's currency. An empty list means
    "accept everything" -- the mock uses this so dev tests don't break
    when a new currency is added to a seed somewhere.

    `tokenization`:
      * `"client"` -- the SDK (Stripe.js, HyperPay COPYandPay, etc.)
        exchanges card data for a token in the browser; the server
        never sees the PAN. Send the resulting token to
        `POST /payment-methods` as `token`.
      * `"server"` -- the gateway's `tokenize()` method runs server-side
        from a synthetic payload. Only the mock uses this; real gateways
        force client-side for PCI scope reasons.

    `supports_3ds` -- whether `authorize()` may return a PENDING intent
    with a `next_action` redirect (3DS challenge / SCA / off-session
    confirmation). Storefronts need to know in advance so they reserve
    UI space for the redirect step.

    `public_credentials` -- gateway-specific, client-safe credentials
    the SDK needs. Always a dict (never None) so the JSON shape is
    stable even when there's nothing to send.
    """

    supported_currencies: list[str]
    tokenization: Tokenization
    supports_3ds: bool
    public_credentials: dict[str, str] = field(default_factory=dict)
