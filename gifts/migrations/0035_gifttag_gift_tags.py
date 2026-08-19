from django.db import migrations, models


TAG_SLUGS = (
    "books",
    "video_games",
    "board_games",
    "movies_tv",
    "music",
    "art_decor",
    "fashion_accessories",
    "beauty_wellness",
    "sports",
    "technology",
    "home",
    "cooking_food",
    "creative_hobbies",
    "travel_experiences",
    "children",
    "other",
)


def create_gift_tags(apps, schema_editor):
    gift_tag = apps.get_model("gifts", "GiftTag")
    gift_tag.objects.bulk_create(
        [gift_tag(slug=slug, position=position) for position, slug in enumerate(TAG_SLUGS)]
    )


def delete_gift_tags(apps, schema_editor):
    apps.get_model("gifts", "GiftTag").objects.filter(slug__in=TAG_SLUGS).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("gifts", "0034_user_last_seen_version"),
    ]

    operations = [
        migrations.CreateModel(
            name="GiftTag",
            fields=[
                (
                    "slug",
                    models.CharField(
                        choices=[
                            ("books", "Books"),
                            ("video_games", "Video games"),
                            ("board_games", "Board games"),
                            ("movies_tv", "Movies and TV"),
                            ("music", "Music"),
                            ("art_decor", "Art and decoration"),
                            ("fashion_accessories", "Fashion and accessories"),
                            ("beauty_wellness", "Beauty and wellness"),
                            ("sports", "Sports"),
                            ("technology", "Technology"),
                            ("home", "Home"),
                            ("cooking_food", "Cooking and food"),
                            ("creative_hobbies", "Creative hobbies"),
                            ("travel_experiences", "Travel and experiences"),
                            ("children", "Children"),
                            ("other", "Other"),
                        ],
                        max_length=32,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("position", models.PositiveSmallIntegerField(unique=True)),
            ],
            options={"ordering": ("position",)},
        ),
        migrations.AddField(
            model_name="gift",
            name="tags",
            field=models.ManyToManyField(blank=True, related_name="gifts", to="gifts.gifttag"),
        ),
        migrations.RunPython(create_gift_tags, delete_gift_tags),
    ]
