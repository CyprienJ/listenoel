import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import urlencode, urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import ExtensionAccessToken, ExtensionAuthorizationCode, Gift, Group

PKCE_RE = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
CODE_TTL = timedelta(minutes=5)
MAX_JSON_BODY = 64 * 1024


def _sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pkce_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _valid_redirect_uri(value):
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and parts.hostname is not None
        and parts.hostname.endswith(".extensions.allizom.org")
        and parts.username is None
        and parts.password is None
        and port is None
        and not parts.query
        and not parts.fragment
    )


def _authorization_parameters(request):
    source = request.POST if request.method == "POST" else request.GET
    redirect_uri = source.get("redirect_uri", "")
    state = source.get("state", "")
    code_challenge = source.get("code_challenge", "")
    if not _valid_redirect_uri(redirect_uri):
        return None
    if not 16 <= len(state) <= 200:
        return None
    if not PKCE_RE.fullmatch(code_challenge):
        return None
    return redirect_uri, state, code_challenge


@require_http_methods(["GET", "POST"])
def extension_authorize(request):
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login

        return redirect_to_login(request.get_full_path())

    parameters = _authorization_parameters(request)
    if parameters is None:
        return HttpResponseBadRequest("Invalid extension authorization request")

    redirect_uri, state, code_challenge = parameters
    if request.method == "GET":
        return render(
            request,
            "gifts/extension_authorize.html",
            {
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": code_challenge,
            },
        )

    raw_code = "ncc_" + secrets.token_urlsafe(32)
    ExtensionAuthorizationCode.objects.create(
        user=request.user,
        code_hash=_sha256(raw_code),
        code_challenge=code_challenge,
        redirect_uri=redirect_uri,
        expires_at=timezone.now() + CODE_TTL,
    )
    query = urlencode({"code": raw_code, "state": state})
    parts = urlsplit(redirect_uri)
    # The destination is restricted above to Firefox's HTTPS identity domain, with
    # credentials, ports, query strings, and fragments rejected.
    return HttpResponseRedirect(urlunsplit((parts.scheme, parts.netloc, parts.path, query, "")))  # NOSONAR


@require_GET
def extension_privacy(request):
    return render(request, "gifts/extension_privacy.html")


def _json_body(request):
    if len(request.body) > MAX_JSON_BODY:
        raise ValueError("Request body is too large")
    try:
        value = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("JSON body must be an object")
    return value


def _api_error(message, status=400):
    return JsonResponse({"error": message}, status=status)


@csrf_exempt  # NOSONAR -- PKCE protects this endpoint; it does not use cookie authentication.
@require_POST
def extension_token(request):
    try:
        data = _json_body(request)
    except ValueError as exc:
        return _api_error(str(exc))

    raw_code = data.get("code", "")
    verifier = data.get("code_verifier", "")
    redirect_uri = data.get("redirect_uri", "")
    if not isinstance(raw_code, str) or not isinstance(verifier, str) or not isinstance(redirect_uri, str):
        return _api_error("Invalid token request")
    if not PKCE_RE.fullmatch(verifier):
        return _api_error("Invalid code verifier")

    with transaction.atomic():
        authorization = (
            ExtensionAuthorizationCode.objects.select_for_update()
            .select_related("user")
            .filter(code_hash=_sha256(raw_code))
            .first()
        )
        now = timezone.now()
        if (
            authorization is None
            or authorization.used_at is not None
            or authorization.expires_at <= now
            or not hmac.compare_digest(authorization.redirect_uri, redirect_uri)
            or not hmac.compare_digest(authorization.code_challenge, _pkce_challenge(verifier))
        ):
            return _api_error("Invalid or expired authorization code", status=401)

        authorization.used_at = now
        authorization.save(update_fields=["used_at"])

        prefix = secrets.token_hex(8)
        raw_token = f"nce_{prefix}_{secrets.token_urlsafe(32)}"
        ExtensionAccessToken.objects.create(
            user=authorization.user,
            token_prefix=prefix,
            token_hash=_sha256(raw_token),
        )

    return JsonResponse({"access_token": raw_token, "token_type": "Bearer"})


def _extension_user(request):
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None, None
    raw_token = header.removeprefix("Bearer ").strip()
    parts = raw_token.split("_", 2)
    if len(parts) != 3 or parts[0] != "nce":
        return None, None
    token = (
        ExtensionAccessToken.objects.select_related("user")
        .filter(
            token_prefix=parts[1],
            revoked_at=None,
            user__is_active=True,
            user__is_verified=True,
        )
        .first()
    )
    if token is None or not hmac.compare_digest(token.token_hash, _sha256(raw_token)):
        return None, None
    token.last_used_at = timezone.now()
    token.save(update_fields=["last_used_at"])
    return token.user, token


def extension_auth(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user, token = _extension_user(request)
        if user is None:
            return _api_error("Authentication required", status=401)
        request.extension_user = user
        request.extension_token = token
        return view(request, *args, **kwargs)

    return wrapped


@require_GET
@extension_auth
def extension_me(request):
    groups = request.extension_user.gift_groups.order_by("name").values("id", "name")
    return JsonResponse(
        {
            "user": {
                "id": request.extension_user.id,
                "nickname": request.extension_user.nickname,
            },
            "groups": list(groups),
        }
    )


def _clean_url(value, field_name, required=False):
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    value = value.strip()
    if not value and not required:
        return ""
    if len(value) > 1000:
        raise ValueError(f"{field_name} is too long")
    try:
        URLValidator(schemes=["http", "https"])(value)
    except ValidationError as exc:
        raise ValueError(f"{field_name} must be an HTTP or HTTPS URL") from exc
    return value


def _clean_price(value):
    if value in (None, ""):
        return None
    try:
        price = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("price must be a decimal number") from exc
    if not price.is_finite() or price < 0 or price > Decimal("99999.99"):
        raise ValueError("price is outside the accepted range")
    return price.quantize(Decimal("0.01"))


@csrf_exempt  # NOSONAR -- bearer-token authentication is not vulnerable to cross-site requests.
@require_POST
@extension_auth
def extension_quick_add(request):
    try:
        data = _json_body(request)
        title = data.get("title", "")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("title is required")
        title = title.strip()
        if len(title) > 200:
            raise ValueError("title is too long")
        source_url = _clean_url(data.get("url", ""), "url", required=True)
        image_url = _clean_url(data.get("image_url", ""), "image_url")
        price = _clean_price(data.get("price"))
        currency = data.get("currency") or "EUR"
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Za-z]{3}", currency):
            raise ValueError("currency must be a three-letter code")
        currency = currency.upper()
        group_ids = data.get("visible_in", [])
        if not isinstance(group_ids, list) or not all(isinstance(value, int) for value in group_ids):
            raise ValueError("visible_in must be a list of group IDs")
    except ValueError as exc:
        return _api_error(str(exc))

    user = request.extension_user
    if Gift.objects.filter(owner=user, url=source_url, offered=False).exists():
        return _api_error("This product is already on your list", status=409)

    with transaction.atomic():
        gift = Gift.objects.create(
            owner=user,
            created_by=user,
            title=title,
            url=source_url,
            image_url=image_url,
            price=price,
            currency=currency,
        )
        if group_ids:
            groups = Group.objects.filter(id__in=group_ids, members=user)
            if groups.count() != len(set(group_ids)):
                transaction.set_rollback(True)
                return _api_error("One or more groups are invalid", status=403)
            gift.visible_in.set(groups)

    return JsonResponse(
        {
            "gift": {
                "id": gift.id,
                "title": gift.title,
                "list_url": f"/list/{user.id}/",
            }
        },
        status=201,
    )


@csrf_exempt  # NOSONAR -- bearer-token authentication is not vulnerable to cross-site requests.
@require_POST
@extension_auth
def extension_revoke(request):
    request.extension_token.revoked_at = timezone.now()
    request.extension_token.save(update_fields=["revoked_at"])
    return HttpResponse(status=204)
