"""
Order, OrderItem, InventoryReservation, Invoice.

Order: snapshot of a converted cart. Address and product fields are
denormalized JSONB / text snapshots so deleting the customer's address
or renaming a product doesn't corrupt order history.

OrderItem: per-line snapshot. Product FK is nullable so we can preserve
order history even if a product is hard-deleted (use case: data
purging for GDPR).

InventoryReservation: holds stock during checkout. Created in Phase 3
of the checkout saga, committed on payment capture, released on cancel
or by the expiry beat task.

Invoice: bonus feature. PDF generation is a stub Celery task.
"""

from apps.orders.models.inventory_reservation import InventoryReservation
from apps.orders.models.invoice import Invoice
from apps.orders.models.order import Order
from apps.orders.models.order_item import OrderItem
from apps.orders.models.order_status import OrderStatus
from apps.orders.models.reservation_status import ReservationStatus

__all__ = [
    "OrderStatus",
    "Order",
    "OrderItem",
    "ReservationStatus",
    "InventoryReservation",
    "Invoice",
]
