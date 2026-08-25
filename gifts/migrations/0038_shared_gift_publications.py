from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def copy_list_publications_to_gifts(apps, schema_editor):
    gift_model = apps.get_model("gifts", "Gift")
    shared_gift_publication_model = apps.get_model("gifts", "SharedGiftPublication")
    shared_list_publication_model = apps.get_model("gifts", "SharedListPublication")

    publications = []
    for list_publication in shared_list_publication_model.objects.all().iterator():
        gift_ids = gift_model.objects.filter(shared_list_id=list_publication.shared_list_id).values_list("id", flat=True)
        for gift_id in gift_ids:
            publications.append(
                shared_gift_publication_model(
                    gift_id=gift_id,
                    group_id=list_publication.group_id,
                    published_by_id=list_publication.published_by_id,
                    created_at=list_publication.created_at,
                )
            )
    shared_gift_publication_model.objects.bulk_create(publications, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("gifts", "0037_shared_lists"),
    ]

    operations = [
        migrations.CreateModel(
            name="SharedGiftPublication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "gift",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shared_publications",
                        to="gifts.gift",
                    ),
                ),
                (
                    "group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shared_gift_publications",
                        to="gifts.group",
                    ),
                ),
                (
                    "published_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="shared_gift_publications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="sharedgiftpublication",
            constraint=models.UniqueConstraint(
                fields=("gift", "group", "published_by"),
                name="unique_shared_gift_publication",
            ),
        ),
        migrations.RunPython(copy_list_publications_to_gifts, migrations.RunPython.noop),
        migrations.DeleteModel(name="SharedListPublication"),
    ]
