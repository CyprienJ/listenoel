from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gifts", "0011_group_show_history"),
    ]

    operations = [
        migrations.AddField(
            model_name="gift",
            name="offered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
