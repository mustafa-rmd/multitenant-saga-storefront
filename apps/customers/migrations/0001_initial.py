import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("tenants", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="Customer",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("email", models.EmailField(max_length=254)),
                ("name", models.CharField(blank=True, max_length=255)),
                ("phone", models.CharField(blank=True, max_length=32)),
                ("customer_type", models.CharField(choices=[("B2C", "Business to consumer"), ("B2B", "Business to business")], default="B2C", max_length=4)),
                ("tax_id", models.CharField(blank=True, max_length=64)),
                ("company_name", models.CharField(blank=True, max_length=255)),
                ("tenant", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, related_name="+", to="tenants.tenant")),
            ],
            options={
                "db_table": "customers_customer",
            },
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.UniqueConstraint(fields=("tenant", "email"), name="uniq_customer_email_per_tenant"),
        ),
        migrations.CreateModel(
            name="Address",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("label", models.CharField(choices=[("shipping", "Shipping"), ("billing", "Billing"), ("both", "Shipping and billing")], default="both", max_length=16)),
                ("country", models.CharField(max_length=2)),
                ("city", models.CharField(max_length=255)),
                ("street", models.CharField(max_length=255)),
                ("postal_code", models.CharField(blank=True, max_length=32)),
                ("is_default", models.BooleanField(default=False)),
                ("customer", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="addresses", to="customers.customer")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, related_name="+", to="tenants.tenant")),
            ],
            options={
                "db_table": "customers_address",
            },
        ),
        migrations.AddIndex(
            model_name="address",
            index=models.Index(fields=["tenant", "customer"], name="customers_a_tenant__idx"),
        ),
    ]
