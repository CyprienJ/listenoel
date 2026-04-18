from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gifts", "0010_reservation_amount_paid"),
    ]

    operations = [
        migrations.AddField(
            model_name="group",
            name="show_history",
            field=models.BooleanField(default=True),
        ),
    ]
