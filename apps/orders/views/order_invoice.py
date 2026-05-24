from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ResourceNotFound
from apps.core.responses import envelope
from apps.orders.models import Invoice, Order


class OrderInvoiceView(APIView):
    """Retrieve the invoice generated for an order.

    Invoices are created asynchronously by the `generate_invoice` Celery
    task after a successful capture, so this endpoint can return
    `404 invoice_not_yet_generated` for a short window after checkout —
    poll or wait for the order webhook. The order itself must belong to
    the authenticated customer (`404` otherwise — we don't disclose
    existence).

    Returns the invoice metadata: `invoice_number` (sequential per tenant),
    `pdf_url` (object-storage URL — MinIO in dev, S3 in prod), and
    `issued_at`.
    """

    @extend_schema(summary="Get the order's invoice")
    def get(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id, customer_id=request.user.id)
        except Order.DoesNotExist as e:
            raise ResourceNotFound("Order not found") from e

        try:
            invoice = order.invoice
        except Invoice.DoesNotExist as e:
            raise ResourceNotFound("Invoice not yet generated for this order") from e

        return Response(
            envelope(
                {
                    "id": str(invoice.id),
                    "order_id": str(order.id),
                    "invoice_number": invoice.invoice_number,
                    "pdf_url": invoice.pdf_url,
                    "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
                },
                request=request,
            )
        )
