from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.carts.serializers import CheckoutResultSerializer, CheckoutSerializer
from apps.core.exceptions import IdempotencyKeyRequired
from apps.core.responses import envelope
from apps.orders.services import CheckoutService


class CartCheckoutView(APIView):
    """Convert the cart to an order and authorize payment.

    **Required header:** `Idempotency-Key`. Retries with the same key
    return the same order without re-charging — defense is layered at
    three places (app short-circuit, DB unique constraint on
    `Order.idempotency_key`, and the gateway's native idempotency cache).

    **Optional header:** `If-Match: <cart.version>`. Strict optimistic
    locking — if the cart has been mutated since the GET, returns
    `409 cart_version_conflict` so the client can re-read before paying.
    Without `If-Match`, a stale view that still validates can proceed.

    Internally a seven-phase saga, each phase committing in its own
    transaction so a worker crash leaves recoverable state. Phases:
    lock cart → validate preconditions (items, addresses, payment, coupons)
    → reserve stock (15-minute TTL, deterministic lock order to avoid
    deadlocks) → create Order + bump coupon uses → authorize via gateway
    → mark cart converted → capture (sync) or wait for webhook (async).
    Any phase failure reverts earlier side-effects.

    Returns `201 Created` for synchronously captured gateways (e.g. mock)
    or `202 Accepted` for async gateways where the capture is pending a
    webhook. Common failures: `400 idempotency_key_required`,
    `409 cart_not_checkout_ready` (missing slot), `409 insufficient_stock`,
    `409 cart_version_conflict`, `402 payment_failed`.
    """

    @extend_schema(summary="Check out the cart (requires Idempotency-Key)")
    def post(self, request):
        idempotency_key = request.META.get("HTTP_IDEMPOTENCY_KEY")
        if not idempotency_key:
            raise IdempotencyKeyRequired()

        if_match = request.META.get("HTTP_IF_MATCH")
        expected_version = int(if_match) if if_match else None

        s = CheckoutSerializer(data=request.data or {})
        s.is_valid(raise_exception=True)

        result = CheckoutService.checkout(
            customer_id=request.user.id,
            idempotency_key=idempotency_key,
            expected_version=expected_version,
            payment_metadata=s.validated_data.get("payment_metadata"),
        )

        data = CheckoutResultSerializer(
            {
                "order_id": result.order.id,
                "order_number": result.order.order_number,
                "status": result.order.status,
                "payment_status": result.payment_status,
                "grand_total": result.order.grand_total,
                "currency": result.order.currency,
                "next_action": result.next_action,
            }
        ).data

        http_status = (
            status.HTTP_201_CREATED
            if result.payment_status == "captured"
            else status.HTTP_202_ACCEPTED
        )
        return Response(envelope(data, request=request), status=http_status)
