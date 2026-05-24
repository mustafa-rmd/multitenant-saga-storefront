import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("tenants", "0001_initial"),
        ("customers", "0001_initial"),
        ("catalog", "0001_initial"),
        ("carts", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="Order",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("order_number", models.BigIntegerField()),
                ("status", models.CharField(choices=[("pending", "Pending (awaiting payment)"), ("paid", "Paid"), ("fulfilled", "Fulfilled"), ("cancelled", "Cancelled"), ("refunded", "Refunded")], default="pending", max_length=16)),
                ("subtotal", models.DecimalField(decimal_places=2, max_digits=12)),
                ("discount_total", models.DecimalField(decimal_places=2, default=0, max_digits=12)),
                ("grand_total", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(max_length=3)),
                ("shipping_address", models.JSONField()),
                ("billing_address", models.JSONField()),
                ("is_b2b", models.BooleanField(default=False)),
                ("tax_id", models.CharField(blank=True, default="", max_length=64)),
                ("idempotency_key", models.CharField(max_length=128, unique=True)),
                ("cart", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="orders", to="carts.cart")),
                ("customer", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="orders", to="customers.customer")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, related_name="+", to="tenants.tenant")),
            ],
            options={
                "db_table": "orders_order",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(fields=("tenant", "order_number"), name="uniq_order_number_per_tenant"),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["tenant", "customer", "-created_at"], name="orders_orde_tenant_cust_idx"),
        ),
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["tenant", "status"], name="orders_orde_tenant_status_idx"),
        ),
        migrations.CreateModel(
            name="OrderItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("product_sku_snapshot", models.CharField(max_length=64)),
                ("product_name_snapshot", models.CharField(max_length=255)),
                ("quantity", models.IntegerField()),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=12)),
                ("line_total", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(max_length=3)),
                ("order", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="items", to="orders.order")),
                ("product", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="+", to="catalog.product")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, related_name="+", to="tenants.tenant")),
            ],
            options={
                "db_table": "orders_orderitem",
            },
        ),
        migrations.CreateModel(
            name="InventoryReservation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("quantity", models.IntegerField()),
                ("expires_at", models.DateTimeField()),
                ("status", models.CharField(choices=[("active", "Active (holding stock)"), ("committed", "Committed (stock deducted)"), ("released", "Released (stock returned)")], default="active", max_length=16)),
                ("cart", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="reservations", to="carts.cart")),
                ("order", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.PROTECT, related_name="reservations", to="orders.order")),
                ("product", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="+", to="catalog.product")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, related_name="+", to="tenants.tenant")),
            ],
            options={
                "db_table": "orders_inventoryreservation",
            },
        ),
        migrations.AddIndex(
            model_name="inventoryreservation",
            index=models.Index(fields=["status", "expires_at"], name="orders_inve_status_expires_idx"),
        ),
        migrations.AddIndex(
            model_name="inventoryreservation",
            index=models.Index(fields=["tenant", "cart"], name="orders_inve_tenant_cart_idx"),
        ),
        migrations.CreateModel(
            name="Invoice",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("invoice_number", models.BigIntegerField()),
                ("pdf_url", models.URLField(blank=True, default="")),
                ("issued_at", models.DateTimeField(blank=True, null=True)),
                ("order", models.OneToOneField(on_delete=models.deletion.PROTECT, related_name="invoice", to="orders.order")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, related_name="+", to="tenants.tenant")),
            ],
            options={
                "db_table": "orders_invoice",
            },
        ),
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.UniqueConstraint(fields=("tenant", "invoice_number"), name="uniq_invoice_number_per_tenant"),
        ),
    ]
