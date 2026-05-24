from django.db import models


class UnscopedManager(models.Manager):
    """Bypass manager. Visible to all tenants; grep for usage to audit."""

    pass
