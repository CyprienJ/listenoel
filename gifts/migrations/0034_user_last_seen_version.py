from django.db import migrations, models


def initialize_existing_users(apps, schema_editor):
    user_model = apps.get_model("gifts", "User")
    user_model.objects.filter(last_seen_version="").update(last_seen_version="1.0.1")


def clear_versions(apps, schema_editor):
    user_model = apps.get_model("gifts", "User")
    user_model.objects.update(last_seen_version="")


class Migration(migrations.Migration):
    dependencies = [
        ("gifts", "0033_giftcomment"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="last_seen_version",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.RunPython(initialize_existing_users, clear_versions),
    ]
