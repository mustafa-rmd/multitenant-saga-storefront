import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0002_payment_order"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcessedWebhookEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("gateway_name", models.CharField(max_length=32)),
                ("event_id", models.CharField(max_length=255)),
                ("event_type", models.CharField(max_length=64)),
                ("processed_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "payments_processedwebhookevent",
            },
        ),
        migrations.AddConstraint(
            model_name="processedwebhookevent",
            constraint=models.UniqueConstraint(
                fields=("gateway_name", "event_id"),
                name="uniq_webhook_event_per_gateway",
            ),
        ),
        migrations.AddIndex(
            model_name="processedwebhookevent",
            index=models.Index(
                fields=["processed_at"],
                name="payments_pr_proc_at_idx",
            ),
        ),
    ]
