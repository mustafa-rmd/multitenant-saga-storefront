import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("tenants", "0001_initial"),
        ("customers", "0001_initial"),
        ("catalog", "0001_initial"),
        ("coupons", "0001_initial"),
        ("payments", "0001_initial"),
    ]
    operations = [
        migrations.CreateModel(
            name="Cart",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("active", "Active"), ("checking_out", "Checking out"), ("converted", "Converted to order"), ("abandoned", "Abandoned")], default="active", max_length=16)),
                ("currency", models.CharField(blank=True, default="", max_length=3)),
                ("version", models.IntegerField(default=0)),
                ("billing_address", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="+", to="customers.address")),
                ("customer", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="carts", to="customers.customer")),
                ("selected_payment_method", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="+", to="payments.paymentmethod")),
                ("shipping_address", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="+", to="customers.address")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, related_name="+", to="tenants.tenant")),
            ],
            options={
                "db_table": "carts_cart",
            },
        ),
        migrations.AddConstraint(
            model_name="cart",
            constraint=models.UniqueConstraint(condition=models.Q(("status", "active")), fields=("customer",), name="one_active_cart_per_customer"),
        ),
        migrations.AddIndex(
            model_name="cart",
            index=models.Index(fields=["tenant", "customer", "status"], name="carts_cart_tenant__idx"),
        ),
        migrations.AddIndex(
            model_name="cart",
            index=models.Index(fields=["tenant", "status", "updated_at"], name="carts_cart_tenant_status_idx"),
        ),
        migrations.CreateModel(
            name="CartItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("quantity", models.IntegerField()),
                ("unit_price_snapshot", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(max_length=3)),
                ("cart", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="items", to="carts.cart")),
                ("product", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="+", to="catalog.product")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, related_name="+", to="tenants.tenant")),
            ],
            options={
                "db_table": "carts_cartitem",
            },
        ),
        migrations.AddConstraint(
            model_name="cartitem",
            constraint=models.UniqueConstraint(fields=("cart", "product"), name="uniq_product_per_cart"),
        ),
        migrations.AddConstraint(
            model_name="cartitem",
            constraint=models.CheckConstraint(check=models.Q(("quantity__gte", 1)), name="cart_item_quantity_positive"),
        ),
        migrations.CreateModel(
            name="AppliedCoupon",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("applied_at", models.DateTimeField(auto_now_add=True)),
                ("cart", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="applied_coupons", to="carts.cart")),
                ("coupon", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="+", to="coupons.coupon")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, related_name="+", to="tenants.tenant")),
            ],
            options={
                "db_table": "carts_appliedcoupon",
            },
        ),
        migrations.AddConstraint(
            model_name="appliedcoupon",
            constraint=models.UniqueConstraint(fields=("cart", "coupon"), name="uniq_coupon_per_cart"),
        ),
    ]
