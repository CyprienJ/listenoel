import datetime
import heapq
import json
import random
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from .models import BalanceSettlement, EventList, Gift, Group, Reservation, User

OFFER_MODAL_CONTENT_PATH = "gifts/includes/_offer_modal_content.html"
RESERVE_MODAL_MODEL_PATH = "gifts/includes/_reserve_modal_content.html"
EDIT_AMOUNTS_PATH = "gifts/includes/_edit_offered_amounts_content.html"
ACCESS_REFUSED_MSG = "You don't have access to this list"
METHOD_NOT_AUTHORIZED_MESSAGE = "Method {} not authorized"
GROUP_NOT_FOUND = "Group not found."
PERMISSION_DENIED = "You don't have permission to do this"
INVALID_AMOUNT_FORMAT = _("Invalid amount format.")


# --- Helpers ---


def _parse_json_body(request):
    try:
        return json.loads(request.body), None
    except ValueError:
        return None, JsonResponse({"success": False, "error": "ValueError: Please provide valid data"}, status=400)
    except TypeError:
        return None, JsonResponse({"success": False, "error": "TypeError: Please provide valid data"}, status=400)


def _redirect_to_referer_or(request, view_name, **kwargs):
    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
    return redirect(view_name, **kwargs)


def _check_gift_access(request, gift):
    is_owner = gift.owner == request.user
    is_reserver = Reservation.objects.filter(gift=gift, reserver=request.user).exists()
    if gift.owner.is_managed:
        mm = getattr(gift.owner, "managed_member_profile", None)
        if mm and request.user in mm.group.members.all():
            return None
    if not (is_owner or is_reserver):
        return HttpResponseForbidden(_(PERMISSION_DENIED))
    return None


def _render_reservation_modal(request, gift, group_id, reservations, extra_exclude_ids=None):
    user_res = next((r for r in reservations if r.reserver_id == request.user.id), None)
    group = get_object_or_404(Group, id=group_id)
    exclude_ids = [request.user.id, gift.owner.id]
    if extra_exclude_ids:
        exclude_ids += list(extra_exclude_ids)
    other_members = group.members.exclude(id__in=exclude_ids)
    context = {
        "item": {
            "current_user": request.user,
            "gift": gift,
            "reservations": reservations,
            "user_reservation": user_res,
            "other_non_participant": other_members,
            "group_id": group_id,
        }
    }
    return render(request, RESERVE_MODAL_MODEL_PATH, context)


def _build_amounts_modal_context(gift, offer_group, reservations):
    givers = list(offer_group.members.exclude(id=gift.owner_id)) if offer_group else []
    payer_res = next((r for r in reservations if r.amount_paid), None) or (reservations[0] if reservations else None)
    pre_payer_id = payer_res.reserver_id if payer_res else None
    split_qs = list(gift.expense_split.values_list("id", flat=True))
    pre_split_ids = split_qs if split_qs else [r.reserver_id for r in reservations]
    return {
        "gift": gift,
        "givers": givers,
        "pre_payer_id": pre_payer_id,
        "pre_split_ids": pre_split_ids,
        "actual_cost": float(gift.actual_cost) if gift.actual_cost else "",
    }


def _apply_payers(gift, payers):
    Reservation.objects.filter(gift=gift).update(amount_paid=None)
    for uid_str, amount_str in payers.items():
        try:
            uid = int(uid_str)
            amount = Decimal(str(amount_str).replace(",", ".")) if amount_str else None
            res, _ = Reservation.objects.get_or_create(gift=gift, reserver_id=uid)
            res.amount_paid = amount
            res.save()
        except (ValueError, InvalidOperation):
            return JsonResponse({"success": False, "error": INVALID_AMOUNT_FORMAT}, status=400)
    return None


# --- Views ---


def redirect_dashboard():
    return redirect("dashboard")


def welcome(request):
    if request.user.is_authenticated:
        if request.user.is_verified:
            return redirect_dashboard()
        else:
            return redirect("verify_email_sent")
    return render(request, "gifts/welcome.html")


@login_required
def dashboard(request):
    user_groups = request.user.gift_groups.all()
    user_event_lists = EventList.objects.filter(owner=request.user)
    participating_event_lists = EventList.objects.filter(participants=request.user).exclude(owner=request.user)
    current_emoji_set = emojis()
    return render(
        request,
        "gifts/dashboard.html",
        {
            "user_groups": user_groups,
            "user_event_lists": user_event_lists,
            "participating_event_lists": participating_event_lists,
            "greeting_emoji": random.choice(current_emoji_set),
            "rain_emojis": current_emoji_set,
        },
    )


def emojis():
    christmas_emojis = ["🎄", "🎁", "🎅", "🤶", "🧑‍🎄", "⛄", "✨", "🌟", "🔔", "🦌"]
    gift_emojis = ["🎁", "🎈", "🎊", "🎉", "✨", "🍰", "🥳", "🎀"]
    if datetime.date.today().month == 12 and datetime.date.today().day <= 25:
        return christmas_emojis
    else:
        return gift_emojis


@login_required
def view_list(request: HttpRequest, user_id: int):
    target_user = User.objects.filter(id=user_id).first()
    if not target_user:
        return render(request, "gifts/user_not_found.html", status=404)

    is_owner = request.user.id == target_user.id
    from_group_id = request.GET.get("from_group")

    group = None
    if from_group_id:
        group = get_object_or_404(Group, id=from_group_id)

    if not is_owner:
        common_groups = Group.objects.filter(members=request.user).filter(members=target_user).exists()
        if not common_groups:
            return render(request, "gifts/user_not_found.html", status=403)

    all_gifts_query: QuerySet[Gift] = Gift.objects.filter(owner=target_user, offered=False).order_by("created_at")

    # Event gifts are only shown to the owner in a separate section
    event_gifts_by_event: list = []
    if is_owner:
        from itertools import groupby as _groupby

        event_qs = (
            all_gifts_query.filter(event_list__isnull=False)
            .select_related("event_list")
            .order_by("event_list_id", "created_at")
        )
        for _eid, grp in _groupby(event_qs, key=lambda g: g.event_list_id):
            gift_group = list(grp)
            event_gifts_by_event.append({"event": gift_group[0].event_list, "gifts": gift_group})
        all_gifts_query = all_gifts_query.filter(event_list__isnull=True)
    else:
        all_gifts_query = all_gifts_query.filter(event_list__isnull=True)

    if from_group_id and not is_owner:
        all_gifts_query = all_gifts_query.filter(
            Q(visible_in__isnull=True) | Q(visible_in__id=from_group_id)
        ).distinct()

    all_gifts = all_gifts_query.prefetch_related("visible_in")
    if target_user.is_managed:
        mm = getattr(target_user, "managed_member_profile", None)
        user_groups = Group.objects.filter(id=mm.group_id) if mm else Group.objects.none()
    else:
        user_groups = request.user.gift_groups.all()

    gifts: list = []
    surprises: list = []

    if is_owner:
        for g in all_gifts:
            if g.created_by == g.owner:
                gifts.append({"gift": g, "is_reserved": None})
    else:
        all_reservations = Reservation.objects.filter(gift__in=all_gifts).select_related("reserver")
        other_members = []
        if group:
            other_members = group.members.exclude(id__in=[request.user.id, target_user.id])

        for gift in all_gifts:
            gift_reservations = [r for r in all_reservations if r.gift_id == gift.id]
            user_res = next((r for r in gift_reservations if r.reserver_id == request.user.id), None)
            participant_ids = {r.reserver_id for r in gift_reservations}
            other_non_participants = [m for m in other_members if m.id not in participant_ids]

            item = {
                "current_user": request.user,
                "gift": gift,
                "reservations": gift_reservations,
                "num_reservations": len(gift_reservations),
                "user_reservation": user_res,
                "other_non_participant": other_non_participants,
                "group_id": from_group_id,
            }
            # Managed user gifts are always shown as wishes, never as surprises
            if gift.created_by == gift.owner or target_user.is_managed:
                gifts.append(item)
            else:
                surprises.append(item)

    return render(
        request,
        "gifts/view_list.html",
        {
            "user": target_user,
            "user_being_viewed": target_user,
            "group": group,
            "gifts": gifts,
            "surprises": surprises,
            "event_gifts_by_event": event_gifts_by_event,
            "is_owner": is_owner,
            "from_group_id": from_group_id,
            "user_groups": user_groups,
            "is_subscribed": request.user.subscriptions.filter(id=target_user.id).exists() if not is_owner else False,
        },
    )


@login_required
@require_POST
def toggle_subscription(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    if target_user == request.user:
        return HttpResponseForbidden(_("You cannot subscribe to yourself"))

    if not Group.objects.filter(members=request.user).filter(members=target_user).exists():
        return HttpResponseForbidden(_(ACCESS_REFUSED_MSG))

    if request.user.subscriptions.filter(id=target_user.id).exists():
        request.user.subscriptions.remove(target_user)
        messages.success(request, _("You are no longer subscribed to %(name)s's list") % {"name": target_user.nickname})
    else:
        request.user.subscriptions.add(target_user)
        messages.success(request, _("You are now subscribed to %(name)s's list") % {"name": target_user.nickname})

    return redirect("view_list", user_id=user_id)


@login_required
def unsubscribe_token(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        target_user = get_object_or_404(User, id=uid)

        if request.user.subscriptions.filter(id=target_user.id).exists():
            request.user.subscriptions.remove(target_user)
            messages.success(
                request, _("You are no longer subscribed to %(name)s's list") % {"name": target_user.nickname}
            )

        return redirect("view_list", user_id=target_user.id)
    except (TypeError, ValueError, OverflowError):
        messages.error(request, _("The unsubscription link is invalid"))
        return redirect_dashboard()


@login_required
@require_POST
def add_gift(request, owner_id):
    owner = get_object_or_404(User, id=owner_id)

    if owner != request.user and not Group.objects.filter(members=request.user).filter(members=owner).exists():
        return HttpResponseForbidden(_(ACCESS_REFUSED_MSG))

    title = request.POST.get("title", "").strip()
    if title:
        gift = Gift.objects.create(
            owner=owner,
            title=title,
            description=request.POST.get("description", "").strip(),
            url=request.POST.get("url", "").strip(),
            created_by=request.user,
        )
        group_ids = request.POST.getlist("visible_in")
        if group_ids:
            valid_groups = Group.objects.filter(id__in=group_ids, members=request.user)
            gift.visible_in.set(valid_groups)

        if owner == request.user:
            subscribers = owner.subscribers.all()
            if subscribers.exists():
                protocol = "https" if request.is_secure() else "http"
                domain = get_current_site(request).domain
                list_url = f"{protocol}://{domain}{reverse('view_list', args=[owner.id])}"

                for subscriber in subscribers:
                    if Group.objects.filter(members=owner).filter(members=subscriber).exists():
                        gift_groups = gift.visible_in.all()
                        if gift_groups.exists() and not gift_groups.filter(members=subscriber).exists():
                            continue

                        uid = urlsafe_base64_encode(force_bytes(owner.pk))
                        token = default_token_generator.make_token(subscriber)
                        unsubscribe_url = f"{protocol}://{domain}{reverse('unsubscribe_token', args=[uid, token])}"

                        context = {
                            "subscriber": subscriber,
                            "owner": owner,
                            "gift": gift,
                            "list_url": list_url,
                            "unsubscribe_url": unsubscribe_url,
                        }
                        subject = _("New gift on %(name)s's list!") % {"name": owner.nickname}
                        html_message = render_to_string("emails/gift_added_notification.html", context)
                        plain_message = render_to_string("emails/gift_added_notification.txt", context)
                        send_mail(
                            subject,
                            plain_message,
                            settings.DEFAULT_FROM_EMAIL,
                            [subscriber.email],
                            html_message=html_message,
                        )

    return _redirect_to_referer_or(request, "view_list", user_id=owner.id)


@login_required
@require_POST
def delete_gift(request, gift_id):
    gift = get_object_or_404(Gift, id=gift_id)
    # Managed member gifts: any group member can delete
    if gift.owner.is_managed:
        mm = getattr(gift.owner, "managed_member_profile", None)
        if not mm or request.user not in mm.group.members.all():
            return HttpResponseForbidden(_(ACCESS_REFUSED_MSG))
        owner_id = gift.owner.id
        gift.delete()
        return _redirect_to_referer_or(request, "view_list", user_id=owner_id)
    if gift.created_by != request.user:
        return HttpResponseForbidden(_(ACCESS_REFUSED_MSG))
    owner_id = gift.owner.id
    gift.delete()
    return _redirect_to_referer_or(request, "view_list", user_id=owner_id)


@login_required
@require_POST
def edit_gift(request: HttpRequest, gift_id: int):
    gift = get_object_or_404(Gift, id=gift_id)

    if gift.owner.is_managed:
        mm = getattr(gift.owner, "managed_member_profile", None)
        if not mm or request.user not in mm.group.members.all():
            return HttpResponseForbidden(_(ACCESS_REFUSED_MSG))
    elif gift.created_by != request.user:
        return HttpResponseForbidden(_(ACCESS_REFUSED_MSG))

    title = request.POST.get("title", "").strip()
    if title:
        gift.title = title
        gift.description = request.POST.get("description", "").strip()
        gift.url = request.POST.get("url", "").strip()
        gift.save()

        group_ids = request.POST.getlist("visible_in")
        if group_ids:
            valid_groups = Group.objects.filter(id__in=group_ids, members=request.user)
            gift.visible_in.set(valid_groups)
        else:
            gift.visible_in.clear()

    return _redirect_to_referer_or(request, "view_list", user_id=gift.owner.id)


@login_required
@require_POST
def edit_gift_price(request, gift_id):
    gift = get_object_or_404(Gift, id=gift_id)

    price_raw = request.POST.get("price", "").strip().replace(",", ".")

    try:
        if price_raw:
            gift.price = Decimal(price_raw)
        else:
            gift.price = None
        gift.save()
        messages.success(request, _("Estimated price updated!"))
    except (InvalidOperation, ValueError):
        messages.error(request, _("Invalid price format."))

    return redirect("view_list", user_id=gift.owner.id)


@login_required
def reserve_gift(request: HttpRequest, gift_id: int):
    if request.method != "POST":
        return JsonResponse({"error": METHOD_NOT_AUTHORIZED_MESSAGE.format(request.method)}, status=405)

    data, err = _parse_json_body(request)
    if err:
        return err

    try:
        exclusivity = data.get("exclusivity")
        user_id = data.get("user_id")
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Unable to find exclusivity"}, status=400)

    gift = get_object_or_404(Gift, id=gift_id)
    user = get_object_or_404(User, id=user_id)

    if gift.owner == request.user:
        return HttpResponseForbidden("Impossible on your own list")

    if not Group.objects.filter(members=request.user).filter(members=gift.owner).exists():
        return HttpResponseForbidden(_(ACCESS_REFUSED_MSG))

    if Reservation.objects.filter(gift=gift, reserver=user).exists():
        return JsonResponse({"success": False, "error": "This person already joined this gift"}, status=409)

    if Reservation.objects.filter(gift=gift, exclusivity=True).exists():
        return JsonResponse({"success": False, "error": "Someone else reserved exclusively this gift"}, status=409)

    Reservation.objects.create(gift=gift, reserver=user, exclusivity=exclusivity)

    group_id = data.get("group_id")
    group = Group.objects.get(id=group_id)

    if not group.members.filter(id=gift.owner.id):
        return HttpResponseForbidden(_(ACCESS_REFUSED_MSG))

    gift.group_reserved_on = group
    gift.save()

    reservations = Reservation.objects.filter(gift=gift).select_related("reserver").order_by("id")
    participant_ids = {r.reserver.id for r in reservations}
    return _render_reservation_modal(request, gift, group_id, reservations, extra_exclude_ids=participant_ids)


@login_required
def modify_reservation(request: HttpRequest, gift_id: int):
    if request.method != "POST":
        return JsonResponse({"error": METHOD_NOT_AUTHORIZED_MESSAGE.format(request.method)}, status=405)

    data, err = _parse_json_body(request)
    if err:
        return err

    gift = get_object_or_404(Gift, id=gift_id)

    try:
        reservation_user_id_to_modify: User = data.get("reservation_user_id_to_modify")
        reservation_user_to_modify = User.objects.get(id=reservation_user_id_to_modify)
        reservation = get_object_or_404(Reservation, gift=gift, reserver=reservation_user_to_modify)
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Unable to find user or reservation"}, status=400)

    if reservation.exclusivity:
        reservation.exclusivity = False
        reservation.save()
    else:
        Reservation.objects.filter(gift=gift).exclude(reserver=reservation_user_to_modify).delete()
        reservation.exclusivity = True
        reservation.save()

    reservations = Reservation.objects.filter(gift=gift).select_related("reserver").order_by("id")
    return _render_reservation_modal(request, gift, data.get("group_id"), reservations)


@login_required
@require_POST
def delete_reservation(request, gift_id):
    if request.method != "POST":
        return JsonResponse({"error": METHOD_NOT_AUTHORIZED_MESSAGE.format(request.method)}, status=405)

    data, err = _parse_json_body(request)
    if err:
        return err

    gift = get_object_or_404(Gift, id=gift_id)
    gift.group_reserved_on = None
    gift.save()

    try:
        reservation_user_id_to_delete: User = data.get("reservation_user_id_to_delete")
        reservation_user_to_delete = User.objects.get(id=reservation_user_id_to_delete)
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Unable to find user or reservation"}, status=400)

    Reservation.objects.filter(gift=gift, reserver=reservation_user_to_delete).delete()

    reservations = Reservation.objects.filter(gift=gift).select_related("reserver").order_by("id")
    return _render_reservation_modal(request, gift, data.get("group_id"), reservations)


@login_required
@require_POST
def offer_gift(request, gift_id):
    gift = get_object_or_404(Gift, id=gift_id)

    if gift.owner == request.user:
        return HttpResponseForbidden(_("You cannot mark your own gift as offered"))

    data, err = _parse_json_body(request)
    if err:
        return err

    reservations = list(Reservation.objects.filter(gift=gift).select_related("reserver").order_by("id"))
    group_id = data.get("group_id")
    confirm = data.get("confirm", False)

    offer_group = gift.group_reserved_on
    if not offer_group and group_id:
        try:
            offer_group = Group.objects.get(id=int(group_id))
        except Group.DoesNotExist:
            return JsonResponse({"success": False, "error": _(GROUP_NOT_FOUND)}, status=404)
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": _("Invalid group ID.")}, status=400)
    history_disabled = offer_group is not None and not offer_group.show_history

    if not confirm:
        context = {
            **_build_amounts_modal_context(gift, offer_group, reservations),
            "group_id": group_id,
            "history_disabled": history_disabled,
        }
        return render(request, OFFER_MODAL_CONTENT_PATH, context)

    if history_disabled:
        gift.delete()
        return JsonResponse({"success": True})

    actual_cost_str = data.get("actual_cost", "")
    if actual_cost_str:
        try:
            gift.actual_cost = Decimal(str(actual_cost_str).replace(",", "."))
        except (InvalidOperation, ValueError):
            return JsonResponse({"success": False, "error": INVALID_AMOUNT_FORMAT}, status=400)

    err = _apply_payers(gift, data.get("payers", {}))
    if err:
        return err

    split_ids = data.get("split_participants", [])
    if split_ids and offer_group:
        gift.expense_split.set(User.objects.filter(id__in=split_ids, gift_groups=offer_group).exclude(id=gift.owner_id))

    res_count = Reservation.objects.filter(gift=gift).count()
    Reservation.objects.filter(gift=gift).update(exclusivity=(res_count == 1))

    if group_id and not gift.group_reserved_on_id:
        try:
            gift.group_reserved_on = Group.objects.get(id=int(group_id))
        except (Group.DoesNotExist, ValueError, TypeError):
            return JsonResponse({"success": False, "error": _(GROUP_NOT_FOUND)}, status=400)

    gift.offered = True
    gift.offered_at = timezone.now()
    gift.save()

    return JsonResponse({"success": True})


@login_required
@require_GET
def history_view(request, group_id=None):
    if not group_id:
        return redirect("dashboard")

    group = get_object_or_404(Group, id=group_id)

    if not group.members.filter(id=request.user.id).exists():
        return render(
            request, "groups/history_access_denied.html", {"group": group, "reason": "not_member"}, status=403
        )

    if not group.show_history:
        return render(
            request,
            "gifts/history.html",
            {
                "group": group,
                "viewing_history": True,
                "history_disabled": True,
                "gifts": [],
                "user_reserved_ids": set(),
            },
        )

    gifts = list(
        Gift.objects.filter(group_reserved_on=group, offered=True)
        .select_related("owner")
        .prefetch_related("reservation__reserver")
        .order_by("-created_at")
    )
    user_reserved_ids = set(
        Reservation.objects.filter(gift__in=gifts, reserver=request.user).values_list("gift_id", flat=True)
    )

    return render(
        request,
        "gifts/history.html",
        {
            "group": group,
            "viewing_history": True,
            "gifts": gifts,
            "user_reserved_ids": user_reserved_ids,
        },
    )


@login_required
@require_POST
def un_offer_gift(request, gift_id):
    gift = get_object_or_404(Gift, id=gift_id, offered=True)
    group = gift.group_reserved_on

    is_owner = gift.owner == request.user
    is_reserver = Reservation.objects.filter(gift=gift, reserver=request.user).exists()
    is_group_member = group is not None and group.members.filter(id=request.user.id).exists()

    if not (is_owner or is_reserver or is_group_member):
        return HttpResponseForbidden(_(PERMISSION_DENIED))

    Reservation.objects.filter(gift=gift).update(amount_paid=None)
    gift.expense_split.clear()
    gift.actual_cost = None
    gift.offered = False
    gift.offered_at = None
    gift.save()

    messages.success(request, _("Gift put back in the list."))
    if group:
        return redirect("history_group", group_id=group.id)
    return redirect("dashboard")


@login_required
@require_POST
def delete_offered_gift(request, gift_id):
    gift = get_object_or_404(Gift, id=gift_id, offered=True)

    err = _check_gift_access(request, gift)
    if err:
        return err

    group = gift.group_reserved_on
    gift.delete()
    messages.success(request, _("Gift deleted."))
    if group:
        return redirect("history_group", group_id=group.id)
    return redirect("dashboard")


@login_required
@require_POST
def edit_offered_amounts(request, gift_id):
    gift = get_object_or_404(Gift, id=gift_id, offered=True)

    err = _check_gift_access(request, gift)
    if err:
        return err

    data, err = _parse_json_body(request)
    if err:
        return err

    reservations = list(Reservation.objects.filter(gift=gift).select_related("reserver").order_by("id"))
    offer_group = gift.group_reserved_on

    if not data.get("save", False):
        return render(request, EDIT_AMOUNTS_PATH, _build_amounts_modal_context(gift, offer_group, reservations))

    actual_cost_str = data.get("actual_cost", "")
    if actual_cost_str:
        try:
            gift.actual_cost = Decimal(str(actual_cost_str).replace(",", "."))
        except (InvalidOperation, ValueError):
            return JsonResponse({"success": False, "error": INVALID_AMOUNT_FORMAT}, status=400)
    else:
        gift.actual_cost = None

    err = _apply_payers(gift, data.get("payers", {}))
    if err:
        return err

    split_ids = data.get("split_participants", [])
    if split_ids and offer_group:
        gift.expense_split.set(User.objects.filter(id__in=split_ids, gift_groups=offer_group).exclude(id=gift.owner_id))
    elif not split_ids:
        gift.expense_split.clear()

    gift.save()
    return JsonResponse({"success": True})


@login_required
@require_POST
def mark_received(request, gift_id):
    gift = get_object_or_404(Gift, id=gift_id)

    if gift.owner != request.user:
        return HttpResponseForbidden(_("Only the gift owner can mark it as received"))

    data, err = _parse_json_body(request)
    if err:
        return err

    confirm = data.get("confirm", False)
    group_id = data.get("group_id")
    reservations = list(Reservation.objects.filter(gift=gift).select_related("reserver").order_by("id"))

    receive_group = gift.group_reserved_on
    if not receive_group and group_id and group_id != "none":
        try:
            receive_group = Group.objects.get(id=int(group_id))
        except Group.DoesNotExist:
            return JsonResponse({"success": False, "error": _("GROUP_NOT_FOUND")}, status=404)
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": _("Invalid group ID.")}, status=400)
    history_disabled = receive_group is not None and not receive_group.show_history

    if not confirm:
        all_groups = list(request.user.gift_groups.all())
        context = {
            "gift": gift,
            "reservations": reservations,
            "group_id": group_id,
            "history_disabled": history_disabled,
            "gift_groups": all_groups,
            "current_group_id": receive_group.id if receive_group else None,
        }
        return render(request, "gifts/includes/_mark_received_content.html", context)

    if group_id == "none":
        gift.group_reserved_on = None
        gift.offered = True
        gift.offered_at = timezone.now()
        gift.save()
        return JsonResponse({"success": True})

    if history_disabled:
        gift.delete()
        return JsonResponse({"success": True})

    if group_id:
        try:
            gift.group_reserved_on = Group.objects.get(id=int(group_id), members=request.user)
        except (Group.DoesNotExist, ValueError, TypeError):
            return JsonResponse({"success": False, "error": _("GROUP_NOT_FOUND")}, status=400)

    gift.offered = True
    gift.offered_at = timezone.now()
    gift.save()

    return JsonResponse({"success": True})


def compute_group_balances(group):
    members = {m.id: m for m in group.members.all()}
    balances = defaultdict(Decimal)

    gifts = (
        Gift.objects.filter(group_reserved_on=group, offered=True, actual_cost__isnull=False)
        .exclude(actual_cost=0)
        .prefetch_related("expense_split", "reservation__reserver")
    )

    for gift in gifts:
        split_users = list(gift.expense_split.all())
        if not split_users:
            continue
        share = gift.actual_cost / len(split_users)
        for u in split_users:
            balances[u.id] -= share
        for res in gift.reservation.all():
            if res.amount_paid:
                balances[res.reserver_id] += res.amount_paid

    for s in BalanceSettlement.objects.filter(group=group):
        balances[s.payer_id] += s.amount
        balances[s.payee_id] -= s.amount

    pos = [(-v, k) for k, v in balances.items() if v > Decimal("0.01")]
    neg = [(v, k) for k, v in balances.items() if v < Decimal("-0.01")]
    heapq.heapify(pos)
    heapq.heapify(neg)

    transactions = []
    while pos and neg:
        credit, cid = heapq.heappop(pos)
        credit = -credit
        debt, did = heapq.heappop(neg)
        amount = min(credit, -debt)  # both credit and -debt are positive
        transactions.append((members.get(did), members.get(cid), amount.quantize(Decimal("0.01"))))
        if credit - amount > Decimal("0.01"):
            heapq.heappush(pos, (-(credit - amount), cid))
        if -debt - amount > Decimal("0.01"):
            heapq.heappush(neg, (debt + amount, did))

    # Unmatched debtors: expense_split was recorded but payer wasn't → show with no creditor
    while neg:
        debt, did = heapq.heappop(neg)
        transactions.append((members.get(did), None, (-debt).quantize(Decimal("0.01"))))

    # Unmatched creditors: payer recorded but no split → show with no debtor
    while pos:
        credit, cid = heapq.heappop(pos)
        transactions.append((None, members.get(cid), credit.quantize(Decimal("0.01"))))

    return (
        {members[uid]: bal.quantize(Decimal("0.01")) for uid, bal in balances.items() if uid in members},
        transactions,
        list(members.values()),
    )


@login_required
@require_GET
def balance_view(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if not group.members.filter(id=request.user.id).exists():
        return render(
            request, "groups/history_access_denied.html", {"group": group, "reason": "not_member"}, status=403
        )
    ctx = {"group": group, "viewing_balance": True}
    if not group.show_balance:
        return render(request, "gifts/balance.html", {**ctx, "balance_disabled": True})
    balances, transactions, members = compute_group_balances(group)
    full_balances = {m: balances.get(m, Decimal("0.00")) for m in members}
    other_members = [m for m in members if m.id != request.user.id]
    all_members = list(members)
    settlements = BalanceSettlement.objects.filter(group=group).select_related("payer", "payee").order_by("-created_at")
    gift_history = (
        Gift.objects.filter(group_reserved_on=group, offered=True)
        .select_related("owner")
        .prefetch_related("reservation__reserver", "expense_split")
        .order_by("-offered_at")
    )
    my_balance = balances.get(request.user, Decimal(0))
    return render(
        request,
        "gifts/balance.html",
        {
            **ctx,
            "balances": full_balances,
            "transactions": transactions,
            "other_members": other_members,
            "all_members": all_members,
            "settlements": settlements,
            "gift_history": gift_history,
            "my_balance": my_balance,
        },
    )


@login_required
@require_POST
def add_settlement(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if not group.members.filter(id=request.user.id).exists():
        return HttpResponseForbidden(_(PERMISSION_DENIED))
    try:
        payee = group.members.get(id=int(request.POST.get("payee_id", "")))
        payer_id = request.POST.get("payer_id")
        payer = group.members.get(id=int(payer_id)) if payer_id else request.user
        if payer == payee:
            raise ValueError("payer == payee")
        amount = Decimal(request.POST.get("amount", "").replace(",", "."))
        if amount <= 0:
            raise ValueError
    except Exception:
        messages.error(request, _("Invalid settlement data."))
        return redirect("balance_group", group_id=group_id)
    BalanceSettlement.objects.create(group=group, payer=payer, payee=payee, amount=amount)
    messages.success(request, _("Settlement recorded."))
    return redirect("balance_group", group_id=group_id)
