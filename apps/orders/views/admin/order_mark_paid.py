"""Admin endpoint: mark a PO order as paid once the invoice clears.

This is the manual counterpart to the gateway capture flow. For card
orders, capture happens automatically in checkout phase 7. For PO orders,
the order stays in PENDING (with payment_status=INVOICE_PENDING) until a
tenant admin confirms the wire/cheque cleared, at which point this
endpoint flips both Payment and Order to their final state.

Idempotent: a second call on an already-PAID order is a no-op and returns
the order as-is. Race-safe via the row lock on the Payment.
"""

from django.db import transaction
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework.response import Response

from apps.core.exceptions import OrderNotCancellable, ResourceNotFound
from apps.core.responses import envelope
from apps.iam.views._base import TenantAdminAPIView
from apps.orders.models import Order
from apps.orders.serializers import AdminOrderSerializer
from apps.payments.models import Payment
from apps.payments.services import PaymentService


class _MarkPaidSerializer(serializers.Serializer):
    """Optional remittance metadata to attach to the Payment.gateway_response."""

    reference = serializers.CharField(required=False, allow_blank=True, default="")


@extend_schema_view(
    post=extend_schema(
        summary="Mark a PO order as paid (admin)",
        request=_MarkPaidSerializer,
        responses={200: AdminOrderSerializer},
    ),
)
class AdminOrderMarkPaidView(TenantAdminAPIView):
    """Flip an INVOICE_PENDING PO payment to CAPTURED and the order to PAID.

    Rejects orders whose payment isn't a PO (card orders go through the
    gateway capture path, not this endpoint).
    """

    lookup_url_kwarg = "order_id"

    def post(self, request, order_id):
        s = _MarkPaidSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        reference = s.validated_data.get("reference") or ""

        try:
            order = Order.objects.select_related("invoice").get(id=order_id)
        except Order.DoesNotExist as exc:
            raise ResourceNotFound("Order not found") from exc

        # Already paid -> idempotent return.
        if order.status == Order.Status.PAID:
            return Response(envelope(AdminOrderSerializer(order).data, request=request))

        if order.status != Order.Status.PENDING:
            raise OrderNotCancellable(
                detail=f"Cannot mark paid: order is in status '{order.status}'",
                meta={"order_id": str(order.id), "status": order.status},
            )

        # Find the PO payment. There should be exactly one in INVOICE_PENDING.
        payment = (
            order.payments.filter(status=Payment.Status.INVOICE_PENDING)
            .order_by("-created_at")
            .first()
        )
        if payment is None:
            raise OrderNotCancellable(
                detail="Order has no invoice-pending payment; not a PO order.",
                meta={"order_id": str(order.id)},
            )

        with transaction.atomic():
            PaymentService.mark_invoice_paid(payment_id=payment.id, reference=reference)
            order.refresh_from_db()
            if order.status != Order.Status.PAID:
                order.status = Order.Status.PAID
                order.save(update_fields=["status", "updated_at"])

        order.refresh_from_db()
        return Response(envelope(AdminOrderSerializer(order).data, request=request))
