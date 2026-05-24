"""Adds PO snapshot fields to Order.

Additive only: existing rows get blank/null values that are ignored by
the gateway-card path.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="payment_terms",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
        migrations.AddField(
            model_name="order",
            name="po_number",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="order",
            name="payment_due_date",
            field=models.DateField(blank=True, null=True),
        ),
    ]
