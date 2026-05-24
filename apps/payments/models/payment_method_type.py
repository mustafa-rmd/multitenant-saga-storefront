from django.db import models


class PaymentMethodType(models.TextChoices):
    CARD = "card", "Card (tokenized via gateway)"
    PURCHASE_ORDER = "purchase_order", "Purchase Order (B2B, invoiced)"
