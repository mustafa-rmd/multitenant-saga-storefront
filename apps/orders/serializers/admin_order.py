from rest_framework import serializers

from apps.orders.models import Order
from apps.orders.serializers.order_item import OrderItemSerializer
from apps.payments.serializers.admin_payment import AdminPaymentSerializer


class AdminOrderSerializer(serializers.ModelSerializer):
    """Operator-facing projection of an Order.

    The storefront `OrderSerializer` deliberately hides payment internals
    (a customer sees `status: "paid"` and nothing else). Admins need to
    answer "which gateway took the money, with which transaction id,
    when, and did the invoice land?" -- so this serializer flattens in:

      * `customerId` -- so list/detail responses identify the buyer
        without a join on the admin side.
      * `payments` -- every Payment attempt, newest first. Multiple rows
        happen when a webhook flipped a status or reconciliation took a
        retry; the history matters for disputes.
      * `invoice` -- whether the post-payment chain completed end-to-end.
        `pdfUrl` empty (or `invoice` null) means Celery hasn't finished
        rendering yet, or the task is stuck and needs operator attention.
    """

    items = OrderItemSerializer(many=True, read_only=True)
    payments = serializers.SerializerMethodField()
    invoice = serializers.SerializerMethodField()
    customer_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "customer_id",
            "status",
            "subtotal",
            "discount_total",
            "grand_total",
            "currency",
            "shipping_address",
            "billing_address",
            "is_b2b",
            "tax_id",
            "payment_terms",
            "po_number",
            "payment_due_date",
            "items",
            "payments",
            "invoice",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_payments(self, order: Order) -> list:
        # Newest first matches how an operator scans for "what was the
        # latest attempt?" Cascades through retries naturally.
        qs = order.payments.select_related("gateway_config").order_by("-created_at")
        return AdminPaymentSerializer(qs, many=True).data

    def get_invoice(self, order: Order) -> dict | None:
        invoice = getattr(order, "invoice", None)
        if invoice is None:
            return None
        return {
            "id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "pdf_url": invoice.pdf_url,
            "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
        }
