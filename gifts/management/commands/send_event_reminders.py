from datetime import date, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from gifts.models import Gift, ReminderDelivery, Subscription


class Command(BaseCommand):
    help = "Send birthday and Christmas reminders due today according to each subscription preference"

    def add_arguments(self, parser):
        parser.add_argument("--date", help="Override today's date (YYYY-MM-DD), primarily for operations and tests")

    def handle(self, *args, **options):
        today = date.fromisoformat(options["date"]) if options.get("date") else timezone.localdate()
        subscriptions = Subscription.objects.select_related("subscriber", "owner").filter(
            subscriber__is_active=True,
            subscriber__is_verified=True,
        )
        sent = 0

        for subscription in subscriptions.filter(christmas_reminder=True).iterator():
            christmas_target = today + timedelta(days=subscription.christmas_reminder_days_before)
            if christmas_target.month == 12 and christmas_target.day == 25:
                sent += self._send([subscription], "christmas", christmas_target)

        for subscription in subscriptions.filter(
            birthday_reminder=True,
            owner__birthday_month__isnull=False,
            owner__birthday_day__isnull=False,
        ).iterator():
            birthday_target = today + timedelta(days=subscription.birthday_reminder_days_before)
            if (
                subscription.owner.birthday_month == birthday_target.month
                and subscription.owner.birthday_day == birthday_target.day
            ):
                sent += self._send([subscription], "birthday", birthday_target)

        self.stdout.write(self.style.SUCCESS(f"Sent {sent} event reminder(s)."))

    def _send(self, subscriptions, event, event_date):
        sent = 0
        base_url = getattr(settings, "PUBLIC_BASE_URL", "https://noscadeaux.fr").rstrip("/")
        for subscription in subscriptions:
            delivery, created = ReminderDelivery.objects.get_or_create(
                subscription=subscription,
                event=event,
                event_year=event_date.year,
            )
            if not created:
                continue

            subscriber = subscription.subscriber
            owner = subscription.owner
            days_before = (
                subscription.birthday_reminder_days_before
                if event == "birthday"
                else subscription.christmas_reminder_days_before
            )
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
                "days_before": days_before,
                "gifts": gifts,
                "list_url": f"{base_url}{reverse('view_list', args=[owner.pk])}",
            }
            if event == "birthday" and days_before == 14:
                subject = _("%(name)s's birthday is in two weeks") % {"name": owner.nickname}
            elif event == "christmas" and days_before == 30:
                subject = _("Christmas is in one month: %(name)s's gift list") % {"name": owner.nickname}
            elif event == "birthday":
                subject = _("%(name)s's birthday is in %(days)s day(s)") % {
                    "name": owner.nickname,
                    "days": days_before,
                }
            else:
                subject = _("Christmas is in %(days)s day(s): %(name)s's gift list") % {
                    "name": owner.nickname,
                    "days": days_before,
                }
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
