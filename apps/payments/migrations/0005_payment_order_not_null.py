"""Bring Payment.order migration state in line with the model.

`0002_payment_order` added the column as `null=True` with a TODO comment
to backfill + enforce NOT NULL later. The model declares it without
`null=True` (i.e. NOT NULL), so `makemigrations` keeps detecting the
divergence. Every Payment row in practice has an order_id, so flipping
NOT NULL is safe here.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0004_purchase_order_method"),
        ("orders", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="order",
            field=models.ForeignKey(
                on_delete=models.deletion.PROTECT,
                related_name="payments",
                to="orders.order",
            ),
        ),
    ]
