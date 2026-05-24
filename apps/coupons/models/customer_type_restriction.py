from django.db import models


class CustomerTypeRestriction(models.TextChoices):
    B2C_ONLY = "B2C", "B2C only"
    B2B_ONLY = "B2B", "B2B only"
    ANY = "any", "Any customer type"
