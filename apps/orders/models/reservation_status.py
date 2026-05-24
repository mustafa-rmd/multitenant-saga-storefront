from django.db import models


class ReservationStatus(models.TextChoices):
    ACTIVE = "active", "Active (holding stock)"
    COMMITTED = "committed", "Committed (stock deducted)"
    RELEASED = "released", "Released (stock returned)"
