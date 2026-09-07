from django.conf import settings
from django.shortcuts import redirect
from django.urls import Resolver404, resolve

from gifts.onboarding import get_onboarding_next_url

COMMON_SETUP_URL_NAMES = {
    "login",
    "logout",
    "welcome",
    "privacy",
    "bug_report",
    "bug_report_success",
    "account/password_reset",
    "account/password_reset_done",
    "account/password_reset_confirm",
    "account/password_reset_complete",
    "set_language",
}

UNVERIFIED_URL_NAMES = COMMON_SETUP_URL_NAMES | {
    "account",
    "verify_email_sent",
    "verify_email_confirm",
    "resend_verification",
    "join_group",
    "group_invitation",
}

PROFILE_SETUP_URL_NAMES = COMMON_SETUP_URL_NAMES | {
    "onboarding_profile",
    "photo_upload_profile",
    "join_group",
    "group_invitation",
}

GROUP_SETUP_URL_NAMES = COMMON_SETUP_URL_NAMES | {
    "onboarding_group",
    "onboarding_join_group",
    "onboarding_group_skip",
    "create_group",
    "join_group",
    "join_group_confirm",
    "dismiss_group_invite",
    "group_invitation",
    "group_invitation_accept",
    "group_invitation_dismiss",
}


def _url_name(path):
    try:
        return resolve(path).url_name
    except Resolver404:
        return None


def _setup_access_is_allowed(request, allowed_url_names):
    if request.path.startswith((settings.STATIC_URL, settings.MEDIA_URL)):
        return True

    try:
        match = resolve(request.path)
    except Resolver404:
        match = None
    if request.user.is_staff and match and match.namespace == "admin":
        return True

    url_name = match.url_name if match else None
    return url_name in allowed_url_names or bool(url_name and url_name.startswith("event_"))


class AccountSetupMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            next_url = get_onboarding_next_url(request.user, request)
            next_url_name = _url_name(next_url)
            current_url_name = _url_name(request.path)

            if next_url_name == "verify_email_sent":
                allowed_url_names = UNVERIFIED_URL_NAMES
            elif next_url_name == "onboarding_profile":
                allowed_url_names = PROFILE_SETUP_URL_NAMES
            elif next_url_name in {"onboarding_group", "join_group", "group_invitation"}:
                allowed_url_names = GROUP_SETUP_URL_NAMES
            else:
                allowed_url_names = None

            if (
                allowed_url_names is not None
                and current_url_name != next_url_name
                and not _setup_access_is_allowed(request, allowed_url_names)
            ):
                return redirect(next_url)

        return self.get_response(request)
