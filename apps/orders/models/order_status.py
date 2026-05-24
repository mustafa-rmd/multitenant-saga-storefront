from django.db import models


class OrderStatus(models.TextChoices):
    PENDING = "pending", "Pending (awaiting payment)"
    PAID = "paid", "Paid"
    FULFILLED = "fulfilled", "Fulfilled"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED = "refunded", "Refunded"
