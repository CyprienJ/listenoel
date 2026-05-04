import contextlib
import json
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from .models import EventList, Gift, GuestReservation

# ── Helpers ──────────────────────────────────────────────────────────────────


def _parse_json_body(request):
    try:
        return json.loads(request.body), None
    except (ValueError, TypeError) as e:
        return None, JsonResponse({"success": False, "error": str(e)}, status=400)


def _get_event_or_404(token):
    return get_object_or_404(EventList, access_token=token)


def _get_guest_identity(request):
    """Return (reserver_user, reserver_name, session_key) for the current request."""
    if request.user.is_authenticated and not request.user.is_managed:
        return request.user, request.user.nickname, ""
    name = request.session.get("guest_name", "")
    sk = request.session.session_key or ""
    return None, name, sk


# ── Public views ─────────────────────────────────────────────────────────────


@require_GET
def event_detail(request, token):
    event = _get_event_or_404(token)
    is_owner = request.user.is_authenticated and request.user == event.owner

    reserver_user, guest_name, session_key = _get_guest_identity(request)
    has_identity = bool(reserver_user or guest_name)

    # All gifts for owner, only visible ones for visitors
    gifts_qs = event.gifts.order_by("created_at")
    if not is_owner:
        gifts_qs = gifts_qs.filter(is_hidden=False)

    # Annotate each gift with reservation state
    gifts_list = []
    for gift in gifts_qs:
        reservations = list(gift.guest_reservations.select_related("reserver_user").all())
        my_res = None
        if reserver_user:
            my_res = next((r for r in reservations if r.reserver_user_id == reserver_user.id), None)
        elif session_key:
            my_res = next((r for r in reservations if r.session_key == session_key), None)
        other_res = [r for r in reservations if r != my_res]
        gifts_list.append(
            {
                "gift": gift,
                "my_reservation": my_res,
                "other_reservations": other_res,
                "has_exclusive_other": any(r.exclusivity for r in other_res),
            }
        )

    # Existing participant names (for identity modal "pick from list")
    participants = (
        GuestReservation.objects.filter(gift__event_list=event)
        .exclude(reserver_name="")
        .values_list("reserver_name", flat=True)
        .distinct()
        .order_by("reserver_name")
    )
    if reserver_user:
        participants = [p for p in participants if p != reserver_user.nickname]

    # Track authenticated visitors so the list appears on their dashboard
    if request.user.is_authenticated and not is_owner:
        event.participants.add(request.user)

    return render(
        request,
        "events/event_detail.html",
        {
            "event": event,
            "is_owner": is_owner,
            "gifts_list": gifts_list,
            "has_identity": has_identity,
            "guest_name": guest_name,
            "reserver_user": reserver_user,
            "participants": list(participants),
            "total_gifts": len(gifts_list),
            "hidden_count": event.gifts.filter(is_hidden=True).count() if is_owner else 0,
            "reserved_count": sum(1 for g in gifts_list if g["my_reservation"] or g["other_reservations"]),
        },
    )


@require_POST
def set_guest_name(request, token):
    event = _get_event_or_404(token)
    data, err = _parse_json_body(request)
    if err:
        return err
    name = (data.get("name") or "").strip()[:100]
    if not name:
        return JsonResponse({"success": False, "error": _("Name required")}, status=400)
    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key
    request.session["guest_name"] = name
    # Transfer anonymous reservations made under this name to the current session
    GuestReservation.objects.filter(
        gift__event_list=event,
        reserver_name__iexact=name,
        reserver_user=None,
    ).exclude(session_key=session_key).update(session_key=session_key)
    return JsonResponse({"success": True, "name": name})


@require_POST
def reserve_event_gift(request, token, gift_id):
    event = _get_event_or_404(token)
    gift = get_object_or_404(Gift, id=gift_id, event_list=event, is_hidden=False)

    reserver_user, reserver_name, session_key = _get_guest_identity(request)
    if not reserver_user and not reserver_name:
        return JsonResponse({"success": False, "error": _("Identity required")}, status=400)

    exclusivity = False
    with contextlib.suppress(ValueError, TypeError):
        body = json.loads(request.body)
        exclusivity = bool(body.get("exclusivity", False))

    if reserver_user:
        existing = GuestReservation.objects.filter(gift=gift, reserver_user=reserver_user).first()
    else:
        if not request.session.session_key:
            request.session.create()
        session_key = request.session.session_key
        existing = GuestReservation.objects.filter(gift=gift, session_key=session_key).first()

    if existing:
        existing.delete()
        return JsonResponse({"success": True, "reserved": False})
    else:
        GuestReservation.objects.create(
            gift=gift,
            reserver_user=reserver_user,
            reserver_name=reserver_name,
            session_key=session_key,
            exclusivity=exclusivity,
        )
        return JsonResponse({"success": True, "reserved": True, "reserver_name": reserver_name})


# ── Owner-only views ─────────────────────────────────────────────────────────


@login_required
@require_POST
def create_event_list(request):
    name = request.POST.get("name", "").strip()
    description = request.POST.get("description", "").strip()
    date_str = request.POST.get("event_date", "").strip()

    if not name:
        return redirect("dashboard")

    event = EventList(
        name=name,
        owner=request.user,
        description=description,
    )
    if date_str:
        with contextlib.suppress(ValueError):
            event.event_date = date.fromisoformat(date_str)
    event.save()
    return redirect("event_detail", token=event.access_token)


def _check_owner(request, event):
    if request.user != event.owner:
        from django.http import HttpResponseForbidden  # noqa: PLC0415

        return HttpResponseForbidden(_("You don't have permission to do this"))
    return None


@login_required
@require_POST
def add_event_gift(request, token):
    event = _get_event_or_404(token)
    err = _check_owner(request, event)
    if err:
        return err
    data, parse_err = _parse_json_body(request)
    if parse_err:
        return parse_err

    title = (data.get("title") or "").strip()
    if not title:
        return JsonResponse({"success": False, "error": _("Title required")}, status=400)

    price = None
    price_str = (data.get("price") or "").strip().replace(",", ".")
    if price_str:
        with contextlib.suppress(InvalidOperation):
            price = Decimal(price_str)

    gift = Gift.objects.create(
        owner=event.owner,
        created_by=event.owner,
        title=title,
        description=(data.get("description") or "").strip(),
        url=(data.get("url") or "").strip(),
        price=price,
        event_list=event,
    )
    return JsonResponse({"success": True, "gift_id": gift.id})


@login_required
@require_POST
def edit_event_gift(request, token, gift_id):
    event = _get_event_or_404(token)
    err = _check_owner(request, event)
    if err:
        return err
    gift = get_object_or_404(Gift, id=gift_id, event_list=event)
    data, parse_err = _parse_json_body(request)
    if parse_err:
        return parse_err

    title = (data.get("title") or "").strip()
    if not title:
        return JsonResponse({"success": False, "error": _("Title required")}, status=400)

    price_str = (data.get("price") or "").strip().replace(",", ".")
    price = None
    if price_str:
        with contextlib.suppress(InvalidOperation):
            price = Decimal(price_str)

    gift.title = title
    gift.description = (data.get("description") or "").strip()
    gift.url = (data.get("url") or "").strip()
    gift.price = price
    gift.save()
    return JsonResponse({"success": True})


@login_required
@require_POST
def delete_event_gift(request, token, gift_id):
    event = _get_event_or_404(token)
    err = _check_owner(request, event)
    if err:
        return err
    gift = get_object_or_404(Gift, id=gift_id, event_list=event)
    gift.delete()
    return redirect("event_detail", token=token)


@login_required
@require_POST
def toggle_event_gift_hidden(request, token, gift_id):
    event = _get_event_or_404(token)
    err = _check_owner(request, event)
    if err:
        return err
    gift = get_object_or_404(Gift, id=gift_id, event_list=event)
    gift.is_hidden = not gift.is_hidden
    gift.save()
    return JsonResponse({"success": True, "hidden": gift.is_hidden})


@login_required
@require_POST
def transfer_event_gift(request, token, gift_id):
    """Move a gift from the event list to the owner's personal wish list (shared with all groups)."""
    event = _get_event_or_404(token)
    err = _check_owner(request, event)
    if err:
        return err
    gift = get_object_or_404(Gift, id=gift_id, event_list=event)
    gift.guest_reservations.all().delete()
    gift.event_list = None
    gift.save()
    user_groups = request.user.gift_groups.all()
    if user_groups.exists():
        gift.visible_in.set(user_groups)
    from django.contrib import messages

    messages.success(request, _("Gift transferred to your wish list."))
    return redirect("event_detail", token=token)


@login_required
@require_POST
def regenerate_event_token(request, token):
    event = _get_event_or_404(token)
    err = _check_owner(request, event)
    if err:
        return err
    event.access_token = uuid.uuid4().hex[:8].upper()
    event.save()
    return redirect("event_detail", token=event.access_token)


@login_required
@require_POST
def event_photo_upload(request, token):
    event = _get_event_or_404(token)
    err = _check_owner(request, event)
    if err:
        return err
    if "image" in request.FILES:
        event.image = request.FILES["image"]
        event.save()
    return redirect("event_detail", token=event.access_token)


@login_required
@require_POST
def edit_event_info(request, token):
    event = _get_event_or_404(token)
    err = _check_owner(request, event)
    if err:
        return err
    name = request.POST.get("name", "").strip()
    if name:
        event.name = name
    event.description = request.POST.get("description", "").strip()
    date_str = request.POST.get("event_date", "").strip()
    if date_str:
        with contextlib.suppress(ValueError):
            event.event_date = date.fromisoformat(date_str)
    else:
        event.event_date = None
    event.save()
    return redirect("event_detail", token=event.access_token)


@login_required
@require_POST
def leave_event_list(request, token):
    """Remove the current user from the event's participants (hides it from their dashboard)."""
    event = _get_event_or_404(token)
    event.participants.remove(request.user)
    return redirect("dashboard")


@login_required
@require_POST
def delete_event_list(request, token):
    event = _get_event_or_404(token)
    err = _check_owner(request, event)
    if err:
        return err
    event.delete()
    return redirect("dashboard")
