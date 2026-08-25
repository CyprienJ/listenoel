import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def verify_turnstile(request, *, action):
    """Validate a single-use Turnstile token for the expected form action."""
    token = request.POST.get("cf-turnstile-response", "")
    if not token or len(token) > 2048:
        return False

    payload = {
        "secret": settings.TURNSTILE_SECRET_KEY,
        "response": token,
    }
    remote_ip = request.META.get("HTTP_CF_CONNECTING_IP") or request.META.get("REMOTE_ADDR")
    if remote_ip:
        payload["remoteip"] = remote_ip

    try:
        response = requests.post(
            settings.TURNSTILE_VERIFY_URL,
            data=payload,
            timeout=settings.TURNSTILE_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError):
        logger.warning("Cloudflare Turnstile validation request failed", exc_info=True)
        return False

    if not result.get("success") or result.get("action") != action:
        logger.info("Cloudflare Turnstile rejected a %s request", action)
        return False
    return True
