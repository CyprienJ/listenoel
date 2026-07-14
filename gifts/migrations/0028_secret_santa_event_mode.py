import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gifts", "0027_store_birthday_without_year"),
    ]

    operations = [
        migrations.AddField(
            model_name="eventlist",
            name="budget_max",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True),
        ),
        migrations.AddField(
            model_name="eventlist",
            name="mode",
            field=models.CharField(
                choices=[("wishlist", "Event wishlist"), ("secret_santa", "Christmas / Secret Santa")],
                default="wishlist",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="SecretSantaExclusion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="secret_santa_exclusions",
                        to="gifts.eventlist",
                    ),
                ),
                (
                    "giver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="secret_santa_exclusions_as_giver",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "receiver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="secret_santa_exclusions_as_receiver",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="SecretSantaAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="secret_santa_assignments",
                        to="gifts.eventlist",
                    ),
                ),
                (
                    "giver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="secret_santa_assignments_as_giver",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "receiver",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="secret_santa_assignments_as_receiver",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="secretsantaexclusion",
            constraint=models.UniqueConstraint(
                fields=("event", "giver", "receiver"), name="unique_secret_santa_exclusion"
            ),
        ),
        migrations.AddConstraint(
            model_name="secretsantaexclusion",
            constraint=models.CheckConstraint(
                condition=~models.Q(giver=models.F("receiver")),
                name="no_self_secret_santa_exclusion",
            ),
        ),
        migrations.AddConstraint(
            model_name="secretsantaassignment",
            constraint=models.UniqueConstraint(fields=("event", "giver"), name="unique_secret_santa_giver"),
        ),
        migrations.AddConstraint(
            model_name="secretsantaassignment",
            constraint=models.UniqueConstraint(fields=("event", "receiver"), name="unique_secret_santa_receiver"),
        ),
        migrations.AddConstraint(
            model_name="secretsantaassignment",
            constraint=models.CheckConstraint(
                condition=~models.Q(giver=models.F("receiver")),
                name="no_self_secret_santa_assignment",
            ),
        ),
    ]
