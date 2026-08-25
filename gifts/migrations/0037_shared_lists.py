import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("gifts", "0036_gift_is_draft"),
    ]

    operations = [
        migrations.CreateModel(
            name="SharedList",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("restore_token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("is_demo", models.BooleanField(default=False)),
            ],
            options={"ordering": ("name", "id")},
        ),
        migrations.CreateModel(
            name="SharedListMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("joined_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "shared_list",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="gifts.sharedlist",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shared_list_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="sharedlist",
            name="members",
            field=models.ManyToManyField(
                related_name="shared_lists",
                through="gifts.SharedListMembership",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.CreateModel(
            name="SharedListPublication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shared_list_publications",
                        to="gifts.group",
                    ),
                ),
                (
                    "published_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shared_list_publications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "shared_list",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="publications",
                        to="gifts.sharedlist",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="gift",
            name="shared_list",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="gifts",
                to="gifts.sharedlist",
            ),
        ),
        migrations.AddConstraint(
            model_name="sharedlistmembership",
            constraint=models.UniqueConstraint(
                fields=("shared_list", "user"),
                name="unique_shared_list_member",
            ),
        ),
        migrations.AddConstraint(
            model_name="sharedlistpublication",
            constraint=models.UniqueConstraint(
                fields=("shared_list", "group", "published_by"),
                name="unique_shared_list_publication",
            ),
        ),
    ]
