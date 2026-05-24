import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="TenantMembership",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("role", models.CharField(choices=[("tenant_admin", "Tenant admin")], default="tenant_admin", max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="memberships", to="tenants.tenant")),
                ("user", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="tenant_memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "iam_tenantmembership",
            },
        ),
        migrations.AddConstraint(
            model_name="tenantmembership",
            constraint=models.UniqueConstraint(fields=("user", "tenant"), name="uniq_membership_per_user_tenant"),
        ),
        migrations.AddIndex(
            model_name="tenantmembership",
            index=models.Index(fields=["tenant", "role"], name="iam_tenantm_tenant__ebdf6b_idx"),
        ),
    ]
