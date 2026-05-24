from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0001_initial"),
    ]
    operations = [
        migrations.AddField(
            model_name="customer",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
    ]
