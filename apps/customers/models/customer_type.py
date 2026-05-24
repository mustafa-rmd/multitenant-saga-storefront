from django.db import models


class CustomerType(models.TextChoices):
    B2C = "B2C", "Business to consumer"
    B2B = "B2B", "Business to business"
