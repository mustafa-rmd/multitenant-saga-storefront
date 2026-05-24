"""
Async tasks for orders:

- generate_invoice: creates the Invoice row, renders a PDF via reportlab,
  uploads it to the configured object store (MinIO in dev, S3 in prod),
  and persists the URL. Idempotent at both the row level and the upload
  level so retries converge instead of duplicating work.
- release_expired_reservations: beat task; reclaims stock from carts
  that started checkout but never completed.
"""

import logging

from celery import shared_task
from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone

from apps.carts.models import Cart
from apps.catalog.models import Product
from apps.core.celery_helpers import DurableTask, TenantAwareTask
from apps.orders.models import (
    InventoryReservation,
    Invoice,
    Order,
    ReservationStatus,
)
from apps.orders.services.invoice_renderer import render_invoice_pdf
from apps.orders.services.invoice_storage import upload_invoice_pdf

log = logging.getLogger(__name__)


@shared_task(
    base=TenantAwareTask,
    bind=True,
    autoretry_for=(Exception,),
    max_retries=5,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
)
def generate_invoice(self, tenant_id: str, order_id: str):
    """Create the invoice row, render its PDF, upload to object storage.

    Split into two idempotent steps so a partial failure (DB row created
    but upload errored — flaky MinIO, S3 throttle, etc.) is recoverable
    by re-running the task: the row stays, the PDF gets a fresh attempt.
    """
    order = Order.objects.select_related("customer").prefetch_related("items").get(id=order_id)

    invoice = getattr(order, "invoice", None)
    if invoice is None:
        invoice = Invoice.objects.create(
            order=order,
            invoice_number=_next_invoice_number(tenant_id),
            issued_at=timezone.now(),
            pdf_url="",
        )
        log.info("Generated invoice #%s for order %s", invoice.invoice_number, order_id)

    if invoice.pdf_url:
        return  # already uploaded; nothing to do

    # Let render/upload exceptions propagate -- autoretry_for picks them up
    # and the row stays in place, so the retry resumes here without
    # reissuing the invoice number. After max_retries the task lands in
    # the dead-letter queue for a human to look at.
    pdf_bytes = render_invoice_pdf(invoice=invoice, order=order)
    url = upload_invoice_pdf(tenant_id=tenant_id, invoice_id=invoice.id, pdf_bytes=pdf_bytes)

    invoice.pdf_url = url
    invoice.save(update_fields=["pdf_url", "updated_at"])
    log.info("Uploaded invoice PDF for order %s -> %s", order_id, url)


def _next_invoice_number(tenant_id: str) -> int:
    # Sequence is provisioned by the platform-admin tenant-create endpoint;
    # see _next_order_number in checkout_helpers.py for the reasoning.
    safe_id = str(tenant_id).replace("-", "_")
    seq_name = f"invoice_number_seq_{safe_id}"
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT nextval('{seq_name}');")
        return cursor.fetchone()[0]


@shared_task(
    base=DurableTask,
    bind=True,
    autoretry_for=(Exception,),
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def release_expired_reservations(self):
    """Beat task: every 30s, release reservations past their TTL.

    Uses skip_locked so we never block on live checkouts. Cross-tenant
    by design -- runs as app_admin (BYPASSRLS).
    """
    now = timezone.now()
    total_released = 0

    while True:
        with transaction.atomic():
            expired = list(
                InventoryReservation.all_objects.select_for_update(skip_locked=True).filter(
                    status=ReservationStatus.ACTIVE, expires_at__lt=now
                )[:100]
            )
            if not expired:
                break

            for res in expired:
                Product.all_objects.filter(id=res.product_id).update(
                    reserved_quantity=F("reserved_quantity") - res.quantity
                )
                res.status = ReservationStatus.RELEASED
                res.save(update_fields=["status", "updated_at"])
                # If the cart is still in checking_out, revert it
                Cart.all_objects.filter(
                    id=res.cart_id,
                    status=Cart.Status.CHECKING_OUT,
                ).update(status=Cart.Status.ACTIVE)
                total_released += 1

    if total_released:
        log.info("Released %s expired reservations", total_released)
