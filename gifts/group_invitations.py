from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urljoin

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Sum
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from gifts.models import Group, GroupInvitationDispatch, User


class InvitationRateLimitError(Exception):
    pass


@dataclass(frozen=True)
class InvitationSendResult:
    requested_count: int
    sent_count: int
    failed_count: int


def build_group_invitation_url(group):
    path = reverse("group_invitation", kwargs={"token": group.invitation_token})
    return urljoin(f"{settings.PUBLIC_BASE_URL.rstrip('/')}/", path.lstrip("/"))


def _used_recipient_quota(queryset):
    return queryset.aggregate(total=Sum("requested_count"))["total"] or 0


def _reserve_invitation_quota(group, sender, requested_count):
    if requested_count > settings.GROUP_INVITATION_MAX_RECIPIENTS_PER_REQUEST:
        raise InvitationRateLimitError

    window_start = timezone.now() - timedelta(seconds=settings.GROUP_INVITATION_RATE_WINDOW_SECONDS)
    with transaction.atomic():
        User.objects.select_for_update().get(pk=sender.pk)
        locked_group = Group.objects.select_for_update().get(pk=group.pk)
        recent_dispatches = GroupInvitationDispatch.objects.filter(created_at__gte=window_start)
        user_total = _used_recipient_quota(recent_dispatches.filter(sender=sender))
        group_total = _used_recipient_quota(recent_dispatches.filter(group=locked_group))
        if (
            user_total + requested_count > settings.GROUP_INVITATION_MAX_RECIPIENTS_PER_USER_WINDOW
            or group_total + requested_count > settings.GROUP_INVITATION_MAX_RECIPIENTS_PER_GROUP_WINDOW
        ):
            raise InvitationRateLimitError
        return GroupInvitationDispatch.objects.create(
            group=locked_group,
            sender=sender,
            requested_count=requested_count,
        )


def send_group_invitations(group, sender, recipients):
    """Send one private message per recipient and retain no recipient address."""
    dispatch = _reserve_invitation_quota(group, sender, len(recipients))
    invitation_url = build_group_invitation_url(group)
    context = {
        "group": group,
        "inviter_name": sender.nickname or sender.email,
        "invitation_url": invitation_url,
    }
    subject = _("Invitation to join %(group_name)s") % {"group_name": group.name}
    message_txt = render_to_string("emails/group_invitation.txt", context)
    message_html = render_to_string("emails/group_invitation.html", context)
    sent_count = 0

    for recipient in recipients:
        try:
            send_mail(
                subject,
                message_txt,
                settings.DEFAULT_FROM_EMAIL,
                [recipient],
                html_message=message_html,
                fail_silently=False,
            )
        except Exception:  # Email providers expose backend-specific exception types.
            continue
        sent_count += 1

    failed_count = len(recipients) - sent_count
    dispatch.sent_count = sent_count
    dispatch.failed_count = failed_count
    dispatch.save(update_fields=["sent_count", "failed_count"])
    return InvitationSendResult(
        requested_count=len(recipients),
        sent_count=sent_count,
        failed_count=failed_count,
    )
