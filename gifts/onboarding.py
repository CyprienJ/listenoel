from django.urls import reverse


CURRENT_ONBOARDING_VERSION = 1


def onboarding_is_complete(user):
    return user.onboarding_version >= CURRENT_ONBOARDING_VERSION


def get_onboarding_next_url(user, request=None):
    """Return the next safe, internal URL for the account setup flow.

    Lot 3 will insert the group choice after the profile. Until then, users
    with a completed profile continue to the dashboard while keeping an
    incomplete, persisted onboarding state.
    """
    if not user.is_authenticated:
        return reverse("welcome")
    if not user.is_verified:
        return reverse("verify_email_sent")
    if user.profile_completed_at is None:
        return reverse("onboarding_profile")
    return reverse("dashboard")
