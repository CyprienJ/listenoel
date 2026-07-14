import django.core.validators
from django.db import migrations, models


def copy_birthday_to_month_day(apps, schema_editor):
    User = apps.get_model("gifts", "User")
    for user in User.objects.exclude(birthday__isnull=True).iterator():
        user.birthday_month = user.birthday.month
        user.birthday_day = user.birthday.day
        user.save(update_fields=["birthday_month", "birthday_day"])


def copy_month_day_to_birthday(apps, schema_editor):
    User = apps.get_model("gifts", "User")
    for user in User.objects.exclude(birthday_month__isnull=True).exclude(birthday_day__isnull=True).iterator():
        user.birthday = f"2000-{user.birthday_month:02d}-{user.birthday_day:02d}"
        user.save(update_fields=["birthday"])


class Migration(migrations.Migration):
    dependencies = [("gifts", "0026_extension_quick_add")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="birthday_month",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(12)],
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="birthday_day",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(31)],
            ),
        ),
        migrations.RunPython(copy_birthday_to_month_day, copy_month_day_to_birthday),
        migrations.RemoveField(model_name="user", name="birthday"),
    ]
