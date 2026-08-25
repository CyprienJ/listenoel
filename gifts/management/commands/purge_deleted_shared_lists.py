from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from gifts.models import SharedList


class Command(BaseCommand):
    help = "Permanently delete shared lists that have been in the trash for more than 48 hours"

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=48)
        queryset = SharedList.objects.filter(deleted_at__lte=cutoff)
        count = queryset.count()
        queryset.delete()
        self.stdout.write(self.style.SUCCESS(f"Purged {count} shared list(s)."))
