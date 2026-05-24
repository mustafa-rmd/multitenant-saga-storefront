"""Adds the purchase-order PaymentMethod variant + INVOICE_PENDING Payment status.

Additive only:
  * PaymentMethod.method_type defaults to 'card' so existing rows are
    unaffected; gateway_config becomes nullable to support PO rows.
  * The CheckConstraint enforces "card => gateway_config NOT NULL,
    purchase_order => gateway_config NULL" so the two variants can't
    drift into invalid states.
  * Payment.status gains a new choice; existing rows keep their value.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0003_processedwebhookevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="paymentmethod",
            name="method_type",
            field=models.CharField(
                choices=[
                    ("card", "Card (tokenized via gateway)"),
                    ("purchase_order", "Purchase Order (B2B, invoiced)"),
                ],
                default="card",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="paymentmethod",
            name="po_account_label",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="paymentmethod",
            name="payment_terms",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AlterField(
            model_name="paymentmethod",
            name="gateway_config",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="payment_methods",
                to="payments.paymentgatewayconfig",
            ),
        ),
        migrations.AlterField(
            model_name="paymentmethod",
            name="token",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddConstraint(
            model_name="paymentmethod",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(method_type="card", gateway_config__isnull=False)
                    | models.Q(method_type="purchase_order", gateway_config__isnull=True)
                ),
                name="paymentmethod_gateway_matches_type",
            ),
        ),
        migrations.AlterField(
            model_name="payment",
            name="gateway_config",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="payments",
                to="payments.paymentgatewayconfig",
            ),
        ),
        migrations.AlterField(
            model_name="payment",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("invoice_pending", "Invoice Pending"),
                    ("authorized", "Authorized"),
                    ("captured", "Captured"),
                    ("failed", "Failed"),
                    ("refunded", "Refunded"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
    ]
