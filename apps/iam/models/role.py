from django.db import models


class Role(models.TextChoices):
    TENANT_ADMIN = "tenant_admin", "Tenant admin"
