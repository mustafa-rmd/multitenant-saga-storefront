import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("tenants", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="Coupon",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("code", models.CharField(max_length=64)),
                ("discount_type", models.CharField(choices=[("percentage", "Percentage"), ("fixed", "Fixed amount")], max_length=16)),
                ("discount_value", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(blank=True, default="", max_length=3)),
                ("min_cart_subtotal", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("allowed_countries", models.JSONField(blank=True, default=list)),
                ("customer_type_restriction", models.CharField(choices=[("B2C", "B2C only"), ("B2B", "B2B only"), ("any", "Any customer type")], default="any", max_length=4)),
                ("max_uses", models.IntegerField(blank=True, null=True)),
                ("uses_count", models.IntegerField(default=0)),
                ("valid_from", models.DateTimeField(blank=True, null=True)),
                ("valid_until", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                ("tenant", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, related_name="+", to="tenants.tenant")),
            ],
            options={
                "db_table": "coupons_coupon",
            },
        ),
        migrations.AddConstraint(
            model_name="coupon",
            constraint=models.UniqueConstraint(fields=("tenant", "code"), name="uniq_coupon_code_per_tenant"),
        ),
    ]
