import calendar
from datetime import date

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from gifts.models import Gift, ReminderDelivery, Subscription


def one_month_after(day):
    year = day.year + (day.month == 12)
    month = day.month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


class Command(BaseCommand):
    help = "Send birthday and Christmas list reminders due one month from today"

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Override today's date (YYYY-MM-DD), primarily for operations and tests")

    def handle(self, *args, **options):
        today = date.fromisoformat(options["date"]) if options.get("date") else timezone.localdate()
        target = one_month_after(today)
        subscriptions = Subscription.objects.select_related("subscriber", "owner").filter(
            subscriber__is_active=True,
            subscriber__is_verified=True,
        )
        sent = 0

        if target.month == 12 and target.day == 25:
            sent += self._send(subscriptions.filter(christmas_reminder=True), "christmas", target)

        birthday_subscriptions = subscriptions.filter(
            birthday_reminder=True,
            owner__birthday__month=target.month,
            owner__birthday__day=target.day,
        )
        sent += self._send(birthday_subscriptions, "birthday", target)
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} event reminder(s)."))

    def _send(self, subscriptions, event, event_date):
        sent = 0
        base_url = getattr(settings, "PUBLIC_BASE_URL", "https://noscadeaux.fr").rstrip("/")
        for subscription in subscriptions.iterator():
            delivery, created = ReminderDelivery.objects.get_or_create(
                subscription=subscription,
                event=event,
                event_year=event_date.year,
            )
            if not created:
                continue

            subscriber = subscription.subscriber
            owner = subscription.owner
            gifts = list(
                Gift.objects.filter(owner=owner, is_hidden=False)
                .filter(Q(visible_in__isnull=True) | Q(visible_in__members=subscriber))
                .distinct()
                .order_by("created_at")
            )
            context = {
                "subscriber": subscriber,
                "owner": owner,
                "event": event,
                "event_date": event_date,
                "gifts": gifts,
                "list_url": f"{base_url}{reverse('view_list', args=[owner.pk])}",
            }
            subject = (
                _("%(name)s's birthday is in one month")
                if event == "birthday"
                else _("Christmas is in one month: %(name)s's gift list")
            ) % {"name": owner.nickname}
            try:
                send_mail(
                    subject,
                    render_to_string("emails/event_reminder.txt", context),
                    settings.DEFAULT_FROM_EMAIL,
                    [subscriber.email],
                    html_message=render_to_string("emails/event_reminder.html", context),
                )
            except Exception:
                delivery.delete()
                raise
            sent += 1
        return sent
