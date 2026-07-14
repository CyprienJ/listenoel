import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models

USER_MODEL = "gifts.user"
GUEST_PARTICIPANT_MODEL = "gifts.secretsantaguestparticipant"


class Migration(migrations.Migration):
    dependencies = [
        ("gifts", "0028_secret_santa_event_mode"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="secretsantaassignment",
            name="unique_secret_santa_giver",
        ),
        migrations.RemoveConstraint(
            model_name="secretsantaassignment",
            name="unique_secret_santa_receiver",
        ),
        migrations.RemoveConstraint(
            model_name="secretsantaassignment",
            name="no_self_secret_santa_assignment",
        ),
        migrations.RemoveConstraint(
            model_name="secretsantaexclusion",
            name="unique_secret_santa_exclusion",
        ),
        migrations.RemoveConstraint(
            model_name="secretsantaexclusion",
            name="no_self_secret_santa_exclusion",
        ),
        migrations.CreateModel(
            name="SecretSantaGuestParticipant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="secret_santa_guest_participants",
                        to="gifts.eventlist",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AlterField(
            model_name="secretsantaassignment",
            name="giver",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="secret_santa_assignments_as_giver",
                to=USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="secretsantaassignment",
            name="receiver",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="secret_santa_assignments_as_receiver",
                to=USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="secretsantaexclusion",
            name="giver",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="secret_santa_exclusions_as_giver",
                to=USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="secretsantaexclusion",
            name="receiver",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="secret_santa_exclusions_as_receiver",
                to=USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="secretsantaassignment",
            name="giver_guest",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="secret_santa_assignments_as_giver",
                to=GUEST_PARTICIPANT_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="secretsantaassignment",
            name="receiver_guest",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="secret_santa_assignments_as_receiver",
                to=GUEST_PARTICIPANT_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="secretsantaexclusion",
            name="giver_guest",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="secret_santa_exclusions_as_giver",
                to=GUEST_PARTICIPANT_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="secretsantaexclusion",
            name="receiver_guest",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="secret_santa_exclusions_as_receiver",
                to=GUEST_PARTICIPANT_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="secretsantaguestparticipant",
            constraint=models.UniqueConstraint(fields=("event", "name"), name="unique_secret_santa_guest_participant"),
        ),
    ]
