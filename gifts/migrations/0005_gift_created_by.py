import django.db.models.deletion
from django.db import migrations, models

def set_default_created_by(apps, schema_editor):
    Gift = apps.get_model('gifts', 'Gift')
    for gift in Gift.objects.all():
        if not gift.created_by:
            gift.created_by = gift.owner
            gift.save(update_fields=['created_by'])

class Migration(migrations.Migration):

    dependencies = [
        ('gifts', '0004_rename_family_group_rename_family_person_group'),
    ]

    operations = [
        migrations.AddField(
            model_name='gift',
            name='created_by',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='created_gifts',
                to='gifts.person'),
        ),
        migrations.RunPython(set_default_created_by),
        migrations.AlterField(
            model_name='gift',
            name='created_by',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='created_gifts',
                to='gifts.person'
            ),
        ),
    ]
