from django.db import models


class CartStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    CHECKING_OUT = "checking_out", "Checking out"
    CONVERTED = "converted", "Converted to order"
    ABANDONED = "abandoned", "Abandoned"
