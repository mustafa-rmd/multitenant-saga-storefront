from django.db import models


class AddressLabel(models.TextChoices):
    SHIPPING = "shipping", "Shipping"
    BILLING = "billing", "Billing"
    BOTH = "both", "Shipping and billing"
