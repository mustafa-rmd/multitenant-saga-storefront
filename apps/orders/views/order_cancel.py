from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.responses import envelope
from apps.orders.serializers import OrderSerializer
from apps.orders.services import CheckoutService


class OrderCancelView(APIView):
    """Cancel a pending order."""

    @extend_schema(summary="Cancel a pending order")
    def post(self, request, order_id):
        """Cancel an order that's still in `pending` status.

        Releases the inventory reservations created during checkout
        (stock becomes available again) and marks any authorized
        payment as `cancelled`. Idempotent: cancelling an already-
        cancelled order returns it unchanged with `200`. Returns the
        updated order envelope.

        Errors:
        - `404 resource_not_found` — order doesn't exist or belongs to
          another customer (cross-customer access is never disclosed).
        - `409 order_not_cancellable` — order is past the cancellable
          window (already paid, fulfilled, or refunded). Use the refund
          endpoint for those cases.

        This endpoint does NOT call the gateway's void API in the POC —
        a hanging payment authorization will be picked up by the
        reconciliation sweeper (out of scope; see README "Deliberately
        out of scope").
        """
        order = CheckoutService.cancel_order(
            customer_id=request.user.id,
            order_id=order_id,
        )
        return Response(envelope(OrderSerializer(order).data, request=request))
