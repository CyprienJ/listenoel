import uuid

from django.db import migrations


def create_users_for_managed_members(apps, schema_editor):
    managed_member = apps.get_model("gifts", "ManagedMember")
    users = apps.get_model("gifts", "User")

    for mm in managed_member.objects.filter(user__isnull=True):
        email = f"managed_{uuid.uuid4().hex[:12]}@noscadeaux.internal"
        user = users.objects.create(
            email=email,
            username=email,
            nickname=mm.name,
            is_managed=True,
            is_verified=True,
            is_active=False,
        )
        mm.user = user
        mm.save(update_fields=["user"])
        mm.group.members.add(user)


def reverse_migration(apps, schema_editor):
    managed_member = apps.get_model("gifts", "ManagedMember")
    for mm in managed_member.objects.filter(user__isnull=False):
        mm.group.members.remove(mm.user)
        mm.user.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("gifts", "0017_managed_member_user_link"),
    ]

    operations = [
        migrations.RunPython(create_users_for_managed_members, reverse_migration),
    ]
