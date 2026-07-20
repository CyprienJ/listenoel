from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from gifts.models import Gift, NotificationDigestPreference, Reservation
from gifts.views import _dashboard_balance_summaries, _upcoming_birthdays

FREQUENCY_INTERVALS = {
    NotificationDigestPreference.FREQUENCY_DAILY: timedelta(days=1),
    NotificationDigestPreference.FREQUENCY_WEEKLY: timedelta(days=7),
    NotificationDigestPreference.FREQUENCY_MONTHLY: timedelta(days=30),
}


class Command(BaseCommand):
    help = "Send notification digests for users whose digest preference is due"

    def handle(self, *args, **options):
        now = timezone.now()
        sent = 0
        preferences = (
            NotificationDigestPreference.objects.select_related("user")
            .filter(
                user__is_active=True,
                user__is_verified=True,
            )
            .exclude(frequency=NotificationDigestPreference.FREQUENCY_NONE)
        )

        for preference in preferences.iterator():
            if not self._is_due(preference, now):
                continue
            if self._send(preference, now):
                sent += 1

        self.stdout.write(self.style.SUCCESS(f"Sent {sent} notification digest(s)."))

    def _is_due(self, preference, now):
        if preference.last_sent_at is None:
            return True
        interval = FREQUENCY_INTERVALS.get(preference.frequency)
        return bool(interval and preference.last_sent_at <= now - interval)

    def _send(self, preference, now):
        user = preference.user
        since = self._since(preference, now)
        groups = user.gift_groups.prefetch_related("members").all()
        recent_group_gifts = (
            Gift.objects.filter(visible_in__members=user, offered=False, event_list__isnull=True)
            .exclude(owner=user)
            .filter(created_at__gte=since)
            .select_related("owner", "created_by")
            .order_by("-created_at")
            .distinct()
        )
        my_reservations = (
            Reservation.objects.filter(reserver=user, gift__offered=False, gift__event_list__isnull=True)
            .select_related("gift", "gift__owner", "gift__group_reserved_on")
            .order_by("-created_at")
        )
        upcoming_birthdays = _upcoming_birthdays(user, groups, timezone.localdate())
        balance_summaries = _dashboard_balance_summaries(user, groups)

        if (
            not recent_group_gifts.exists()
            and not my_reservations.exists()
            and not upcoming_birthdays
            and not balance_summaries
        ):
            preference.last_sent_at = now
            preference.save(update_fields=["last_sent_at"])
            return False

        base_url = getattr(settings, "PUBLIC_BASE_URL", "https://noscadeaux.fr").rstrip("/")
        context = {
            "user": user,
            "frequency": preference.get_frequency_display(),
            "recent_group_gifts": list(recent_group_gifts[:20]),
            "my_reservations": list(my_reservations[:20]),
            "upcoming_birthdays": upcoming_birthdays,
            "balance_summaries": balance_summaries,
            "notification_center_url": f"{base_url}{reverse('notification_center')}",
        }
        send_mail(
            _("Your nosCadeaux notification digest"),
            render_to_string("emails/notification_digest.txt", context),
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=render_to_string("emails/notification_digest.html", context),
        )

        preference.last_sent_at = now
        preference.save(update_fields=["last_sent_at"])
        return True

    def _since(self, preference, now):
        if preference.last_sent_at is not None:
            return preference.last_sent_at
        interval = FREQUENCY_INTERVALS.get(preference.frequency, timedelta(days=7))
        return now - interval
