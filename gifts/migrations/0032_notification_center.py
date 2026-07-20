from django.conf import settings
from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("gifts", "0031_photo_presets"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="birthday_reminder_days_before",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (0, "On the day"),
                    (1, "1 day before"),
                    (7, "1 week before"),
                    (14, "2 weeks before"),
                    (30, "1 month before"),
                ],
                default=14,
                validators=[django.core.validators.MaxValueValidator(365)],
            ),
        ),
        migrations.AddField(
            model_name="subscription",
            name="christmas_reminder_days_before",
            field=models.PositiveSmallIntegerField(
                choices=[
                    (0, "On the day"),
                    (1, "1 day before"),
                    (7, "1 week before"),
                    (14, "2 weeks before"),
                    (30, "1 month before"),
                ],
                default=30,
                validators=[django.core.validators.MaxValueValidator(365)],
            ),
        ),
        migrations.CreateModel(
            name="NotificationDigestPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "frequency",
                    models.CharField(
                        choices=[
                            ("none", "Disabled"),
                            ("daily", "Daily"),
                            ("weekly", "Weekly"),
                            ("monthly", "Monthly"),
                        ],
                        default="none",
                        max_length=10,
                    ),
                ),
                ("last_sent_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notification_digest_preference",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
