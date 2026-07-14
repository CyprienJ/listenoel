from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gifts", "0030_demo_scope"),
    ]

    operations = [
        migrations.AddField(
            model_name="group",
            name="image_preset",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="user",
            name="avatar_preset",
            field=models.CharField(blank=True, max_length=255),
        ),
    ]
