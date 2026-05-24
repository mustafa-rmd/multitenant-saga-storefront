import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("tenants", "0001_initial"),
        ("customers", "0001_initial"),
        # Note: orders is created AFTER payments to avoid circular refs.
        # Payment.order FK is added in a follow-up migration (see 0002).
    ]
    operations = [
        migrations.CreateModel(
            name="PaymentGatewayConfig",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("gateway_name", models.CharField(choices=[("mock", "Mock (test gateway)"), ("stripe", "Stripe"), ("hyperpay", "HyperPay"), ("tap", "Tap")], max_length=32)),
                ("credentials", models.JSONField(default=dict)),
                ("is_active", models.BooleanField(default=True)),
                ("is_default", models.BooleanField(default=False)),
                ("tenant", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, related_name="+", to="tenants.tenant")),
            ],
            options={
                "db_table": "payments_paymentgatewayconfig",
            },
        ),
        migrations.AddConstraint(
            model_name="paymentgatewayconfig",
            constraint=models.UniqueConstraint(fields=("tenant", "gateway_name"), name="uniq_gateway_per_tenant"),
        ),
        migrations.AddConstraint(
            model_name="paymentgatewayconfig",
            constraint=models.UniqueConstraint(condition=models.Q(("is_default", True)), fields=("tenant",), name="one_default_gateway_per_tenant"),
        ),
        migrations.CreateModel(
            name="PaymentMethod",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("token", models.CharField(max_length=255)),
                ("brand", models.CharField(blank=True, max_length=32)),
                ("last_four", models.CharField(blank=True, max_length=4)),
                ("is_default", models.BooleanField(default=False)),
                ("customer", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="payment_methods", to="customers.customer")),
                ("gateway_config", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="payment_methods", to="payments.paymentgatewayconfig")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, related_name="+", to="tenants.tenant")),
            ],
            options={
                "db_table": "payments_paymentmethod",
            },
        ),
        migrations.AddConstraint(
            model_name="paymentmethod",
            constraint=models.UniqueConstraint(condition=models.Q(("is_default", True)), fields=("customer",), name="one_default_method_per_customer"),
        ),
        migrations.AddIndex(
            model_name="paymentmethod",
            index=models.Index(fields=["tenant", "customer"], name="payments_pa_tenant__idx"),
        ),
        migrations.CreateModel(
            name="Payment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("authorized", "Authorized"), ("captured", "Captured"), ("failed", "Failed"), ("refunded", "Refunded"), ("cancelled", "Cancelled")], default="pending", max_length=16)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("currency", models.CharField(max_length=3)),
                ("gateway_transaction_id", models.CharField(blank=True, default="", max_length=255)),
                ("idempotency_key", models.CharField(max_length=128, unique=True)),
                ("gateway_response", models.JSONField(blank=True, default=dict)),
                ("gateway_config", models.ForeignKey(on_delete=models.deletion.PROTECT, related_name="payments", to="payments.paymentgatewayconfig")),
                ("tenant", models.ForeignKey(db_index=True, on_delete=models.deletion.CASCADE, related_name="+", to="tenants.tenant")),
                # order FK added in 0002 to break circular import
            ],
            options={
                "db_table": "payments_payment",
            },
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(fields=["gateway_transaction_id"], name="payments_pa_gateway_idx"),
        ),
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(fields=["tenant", "status"], name="payments_pa_tenant_status_idx"),
        ),
    ]
