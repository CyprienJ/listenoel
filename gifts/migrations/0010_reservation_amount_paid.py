from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gifts', '0009_add_avatar_to_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='reservation',
            name='amount_paid',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=7, null=True),
        ),
    ]
