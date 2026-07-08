from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("gifts", "0025_birthday_reminders"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gift",
            name="url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="gift",
            name="currency",
            field=models.CharField(default="EUR", max_length=3),
        ),
        migrations.AddField(
            model_name="gift",
            name="image_url",
            field=models.URLField(blank=True, max_length=1000),
        ),
        migrations.CreateModel(
            name="ExtensionAuthorizationCode",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code_hash", models.CharField(max_length=64, unique=True)),
                ("code_challenge", models.CharField(max_length=128)),
                ("redirect_uri", models.URLField(max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extension_authorization_codes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ExtensionAccessToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_prefix", models.CharField(db_index=True, max_length=16, unique=True)),
                ("token_hash", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extension_access_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
