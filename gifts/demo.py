from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.utils.translation import gettext as _

DEMO_EMAIL = "demo@noscadeaux.internal"
DEMO_PASSWORD = None
DEMO_RESET_INTERVAL = timedelta(minutes=getattr(settings, "DEMO_RESET_INTERVAL_MINUTES", 15))


def is_demo_user(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_demo", False))


def has_same_demo_scope(user, obj) -> bool:
    return bool(getattr(user, "is_demo", False)) == bool(getattr(obj, "is_demo", False))


def demo_scope_forbidden_response():
    return HttpResponseForbidden(_("Demo and real accounts cannot be mixed."))


def demo_reset_due(user) -> bool:
    return not user or timezone.now() - user.date_joined >= DEMO_RESET_INTERVAL
