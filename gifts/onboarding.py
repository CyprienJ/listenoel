from django.urls import reverse
from django.utils import timezone

CURRENT_ONBOARDING_VERSION = 1
PENDING_GROUP_INVITE_SESSION_KEY = "pending_group_invite_token"


def onboarding_is_complete(user):
    return user.onboarding_version >= CURRENT_ONBOARDING_VERSION


def get_pending_group_invite(user, request=None):
    """Return a validated invitation identifier, never an arbitrary return URL."""
    if request is not None:
        token = request.session.get(PENDING_GROUP_INVITE_SESSION_KEY, "")
        if token:
            return token
    if getattr(user, "is_authenticated", False):
        return user.pending_group_invite_token
    return ""


def remember_pending_group_invite(request, token, user=None):
    token = (token or "").strip()
    if not token:
        return

    request.session[PENDING_GROUP_INVITE_SESSION_KEY] = token
    target_user = user or request.user
    if getattr(target_user, "is_authenticated", False) and target_user.pending_group_invite_token != token:
        target_user.pending_group_invite_token = token
        target_user.save(update_fields=["pending_group_invite_token"])


def clear_pending_group_invite(request, user=None):
    request.session.pop(PENDING_GROUP_INVITE_SESSION_KEY, None)
    target_user = user or request.user
    if getattr(target_user, "is_authenticated", False) and target_user.pending_group_invite_token:
        target_user.pending_group_invite_token = ""
        target_user.save(update_fields=["pending_group_invite_token"])


def complete_onboarding(user):
    update_fields = []
    if user.onboarding_version < CURRENT_ONBOARDING_VERSION:
        user.onboarding_version = CURRENT_ONBOARDING_VERSION
        update_fields.append("onboarding_version")
    if user.onboarding_completed_at is None:
        user.onboarding_completed_at = timezone.now()
        update_fields.append("onboarding_completed_at")
    if update_fields:
        user.save(update_fields=update_fields)


def get_onboarding_next_url(user, request=None):
    """Return the next safe, internal URL for the account setup flow."""
    if not user.is_authenticated:
        return reverse("welcome")
    if not user.is_verified:
        return reverse("verify_email_sent")
    if user.profile_completed_at is None:
        return reverse("onboarding_profile")
    if not onboarding_is_complete(user):
        pending_token = get_pending_group_invite(user, request)
        if pending_token:
            return reverse("join_group", kwargs={"token": pending_token})
        return reverse("onboarding_group")
    return reverse("dashboard")
