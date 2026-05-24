import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("tenants", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("sku", models.CharField(max_length=64)),
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True)),
                ("price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(max_length=3)),
                ("stock_quantity", models.IntegerField(default=0)),
                ("reserved_quantity", models.IntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("tenant", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, related_name="+", to="tenants.tenant")),
            ],
            options={
                "db_table": "catalog_product",
            },
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.UniqueConstraint(fields=("tenant", "sku"), name="uniq_product_sku_per_tenant"),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(check=models.Q(("stock_quantity__gte", models.F("reserved_quantity"))), name="stock_gte_reserved"),
        ),
        migrations.AddConstraint(
            model_name="product",
            constraint=models.CheckConstraint(check=models.Q(("price__gte", 0)), name="price_non_negative"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["tenant", "is_active"], name="catalog_pro_tenant__idx"),
        ),
    ]
