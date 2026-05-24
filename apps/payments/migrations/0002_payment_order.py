"""Adds the Payment.order FK -- separate migration to break the circular
dependency between payments and orders apps."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0001_initial"),
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="order",
            field=models.ForeignKey(
                on_delete=models.deletion.PROTECT,
                related_name="payments",
                to="orders.order",
                # Default required since this is being added to a non-empty
                # field at migration time. The DB has no payments yet, so
                # this is effectively a no-op cast.
                null=True,
            ),
        ),
        # In a real follow-up we'd backfill and then enforce NOT NULL.
        # For the POC: leaving nullable is fine since the table is empty
        # when this migration runs.
        migrations.AddIndex(
            model_name="payment",
            index=models.Index(
                fields=["order", "status"],
                name="payments_pa_order_status_idx",
            ),
        ),
    ]
