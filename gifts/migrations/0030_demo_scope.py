from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gifts", "0029_secret_santa_guest_participants"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventlist",
            name="is_demo",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="group",
            name="is_demo",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="is_demo",
            field=models.BooleanField(default=False),
        ),
    ]
