import datetime
import json
import random
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

from .models import Gift, Group, Reservation, User

OFFER_MODAL_CONTENT_PATH = "gifts/includes/_offer_modal_content.html"

RESERVE_MODAL_MODEL_PATH = "gifts/includes/_reserve_modal_content.html"
ACCESS_REFUSED_MSG = "You don't have access to this list"
VALUE_ERROR_MSG = "ValueError: Please provide valid data"
TYPE_ERROR_MSG = "TypeError: Please provide valid data"
METHOD_NOT_AUTHORIZED_MESSAGE = "Method {} not authorized"
GROUP_NOT_FOUND = "Group not found."
PERMISSION_DENIED = "You don't have permission to do this"


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

    current_emoji_set = emojis()

    return render(
        request,
        "gifts/dashboard.html",
        {
            "user_groups": user_groups,
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

    if from_group_id and not is_owner:
        all_gifts_query = all_gifts_query.filter(
            Q(visible_in__isnull=True) | Q(visible_in__id=from_group_id)
        ).distinct()

    all_gifts = all_gifts_query.prefetch_related("visible_in")
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
            if gift.created_by == gift.owner:
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

    # Security check: can only add to own list or list of someone in common group
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
            # Security check: can only set visibility for groups user is member of
            valid_groups = Group.objects.filter(id__in=group_ids, members=request.user)
            gift.visible_in.set(valid_groups)

        # Send notification to all subscribers of the owner
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
    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)

    return redirect("view_list", user_id=owner.id)


@login_required
@require_POST
def delete_gift(request, gift_id):
    gift = get_object_or_404(Gift, id=gift_id, created_by=request.user)
    owner_id = gift.owner.id
    gift.delete()
    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)

    return redirect("view_list", user_id=owner_id)


@login_required
@require_POST
def edit_gift(request: HttpRequest, gift_id: int):
    # Only the creator can edit the gift
    gift = get_object_or_404(Gift, id=gift_id, created_by=request.user)

    title = request.POST.get("title", "").strip()

    if title:
        gift.title = title
        gift.description = request.POST.get("description", "").strip()
        gift.url = request.POST.get("url", "").strip()
        gift.save()

        group_ids = request.POST.getlist("visible_in")
        if group_ids:
            # Security check: can only set visibility for groups user is member of
            valid_groups = Group.objects.filter(id__in=group_ids, members=request.user)
            gift.visible_in.set(valid_groups)
        else:
            gift.visible_in.clear()

    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
    owner_id = gift.owner.id
    return redirect("view_list", user_id=owner_id)


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

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"success": False, "error": VALUE_ERROR_MSG}, status=400)
    except TypeError:
        return JsonResponse({"success": False, "error": TYPE_ERROR_MSG}, status=400)

    try:
        exclusivity = data.get("exclusivity")
        user_id = data.get("user_id")
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Unable to find exclusivity"}, status=400)

    gift = get_object_or_404(Gift, id=gift_id)
    user = get_object_or_404(User, id=user_id)

    if gift.owner == request.user:
        return HttpResponseForbidden("Impossible on your own list")

    # Common group verification
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

    reservations = Reservation.objects.filter(gift=gift).order_by("id")

    user_res = next((r for r in reservations if r.reserver_id == request.user.id), None)

    user_already_participating = (r.reserver.id for r in reservations)

    group = get_object_or_404(Group, id=group_id)
    other_members = group.members.exclude(id__in=[request.user.id, gift.owner.id]).exclude(
        id__in=user_already_participating
    )

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


@login_required
def modify_reservation(request: HttpRequest, gift_id: int):
    if request.method != "POST":
        return JsonResponse({"error": METHOD_NOT_AUTHORIZED_MESSAGE.format(request.method)}, status=405)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"success": False, "error": VALUE_ERROR_MSG}, status=400)
    except TypeError:
        return JsonResponse({"success": False, "error": TYPE_ERROR_MSG}, status=400)

    gift = get_object_or_404(Gift, id=gift_id)

    try:
        reservation_user_id_to_modify: User = data.get("reservation_user_id_to_modify")
        reservation_user_to_modify = User.objects.get(id=reservation_user_id_to_modify)
        reservation = get_object_or_404(Reservation, gift=gift, reserver=reservation_user_to_modify)
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Unable to find user or reservation"}, status=400)

    if reservation.exclusivity:
        # switch it to non-exclusive
        reservation.exclusivity = False
        reservation.save()

    else:
        # Remove all other reservations and switch it to exclusivity
        Reservation.objects.filter(gift=gift).exclude(reserver=reservation_user_to_modify).delete()

        reservation.exclusivity = True
        reservation.save()

    reservations = Reservation.objects.filter(gift=gift).order_by("id")

    user_res = next((r for r in reservations if r.reserver_id == request.user.id), None)

    group_id = data.get("group_id")
    group = get_object_or_404(Group, id=group_id)
    other_members = group.members.exclude(id__in=[request.user.id, gift.owner.id])

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


@login_required
@require_POST
def delete_reservation(request, gift_id):
    if request.method != "POST":
        return JsonResponse({"error": METHOD_NOT_AUTHORIZED_MESSAGE.format(request.method)}, status=405)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"success": False, "error": VALUE_ERROR_MSG}, status=400)
    except TypeError:
        return JsonResponse({"success": False, "error": TYPE_ERROR_MSG}, status=400)

    gift = get_object_or_404(Gift, id=gift_id)
    gift.group_reserved_on = None
    gift.save()

    try:
        reservation_user_id_to_delete: User = data.get("reservation_user_id_to_delete")
        reservation_user_to_delete = User.objects.get(id=reservation_user_id_to_delete)
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Unable to find user or reservation"}, status=400)

    reservation_to_delete = Reservation.objects.filter(gift=gift, reserver=reservation_user_to_delete)

    reservation_to_delete.delete()

    reservations = Reservation.objects.filter(gift=gift).order_by("id")

    user_res = next((r for r in reservations if r.reserver_id == request.user.id), None)

    group_id = data.get("group_id")
    group = get_object_or_404(Group, id=group_id)
    other_members = group.members.exclude(id__in=[request.user.id, gift.owner.id])

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


@login_required
@require_POST
def offer_gift(request, gift_id):
    gift = get_object_or_404(Gift, id=gift_id)

    if not Reservation.objects.filter(gift=gift, reserver=request.user).exists():
        return HttpResponseForbidden(_("Only reservers can mark a gift as offered"))

    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": VALUE_ERROR_MSG}, status=400)

    reservations = list(Reservation.objects.filter(gift=gift).select_related("reserver").order_by("id"))
    group_id = data.get("group_id")
    confirm = data.get("confirm", False)

    # Determine the group to check show_history
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
            "gift": gift,
            "reservations": reservations,
            "group_id": group_id,
            "history_disabled": history_disabled,
        }
        return render(request, OFFER_MODAL_CONTENT_PATH, context)

    if history_disabled:
        gift.delete()
        return JsonResponse({"success": True})

    amounts = data.get("amounts", {})
    if amounts:
        for reservation in reservations:
            amount_str = amounts.get(str(reservation.reserver.id), "")
            if amount_str:
                try:
                    reservation.amount_paid = Decimal(str(amount_str).replace(",", "."))
                    reservation.save()
                except (InvalidOperation, ValueError):
                    return JsonResponse({"success": False, "error": _("Invalid amount format.")}, status=400)

    if group_id and not gift.group_reserved_on_id:
        try:
            gift.group_reserved_on = Group.objects.get(id=int(group_id))
        except (Group.DoesNotExist, ValueError, TypeError):
            return JsonResponse({"success": False, "error": _("GROUP_NOT_FOUND")}, status=400)

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

    is_owner = gift.owner == request.user
    is_reserver = Reservation.objects.filter(gift=gift, reserver=request.user).exists()

    if not (is_owner or is_reserver):
        return HttpResponseForbidden(_(PERMISSION_DENIED))

    group = gift.group_reserved_on
    Reservation.objects.filter(gift=gift).update(amount_paid=None)
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

    is_owner = gift.owner == request.user
    is_reserver = Reservation.objects.filter(gift=gift, reserver=request.user).exists()

    if not (is_owner or is_reserver):
        return HttpResponseForbidden(_(PERMISSION_DENIED))

    group = gift.group_reserved_on
    gift.delete()
    messages.success(request, _("Gift deleted."))
    if group:
        return redirect("history_group", group_id=group.id)
    return redirect("dashboard")


EDIT_AMOUNTS_PATH = "gifts/includes/_edit_offered_amounts_content.html"


@login_required
@require_POST
def edit_offered_amounts(request, gift_id):
    gift = get_object_or_404(Gift, id=gift_id, offered=True)

    is_owner = gift.owner == request.user
    is_reserver = Reservation.objects.filter(gift=gift, reserver=request.user).exists()

    if not (is_owner or is_reserver):
        return HttpResponseForbidden(_(PERMISSION_DENIED))

    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": VALUE_ERROR_MSG}, status=400)

    reservations = list(Reservation.objects.filter(gift=gift).select_related("reserver").order_by("id"))
    save = data.get("save", False)

    if not save:
        context = {"gift": gift, "reservations": reservations}
        return render(request, EDIT_AMOUNTS_PATH, context)

    amounts = data.get("amounts", {})
    for reservation in reservations:
        amount_str = amounts.get(str(reservation.reserver.id), "")
        if amount_str:
            try:
                reservation.amount_paid = Decimal(str(amount_str).replace(",", "."))
            except (InvalidOperation, ValueError):
                return JsonResponse({"success": False, "error": _("Invalid amount format.")}, status=400)
        else:
            reservation.amount_paid = None
        reservation.save()

    return JsonResponse({"success": True})


@login_required
@require_POST
def mark_received(request, gift_id):
    gift = get_object_or_404(Gift, id=gift_id)

    if gift.owner != request.user:
        return HttpResponseForbidden(_("Only the gift owner can mark it as received"))

    try:
        data = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": VALUE_ERROR_MSG}, status=400)

    confirm = data.get("confirm", False)
    group_id = data.get("group_id")
    reservations = list(Reservation.objects.filter(gift=gift).select_related("reserver").order_by("id"))

    # Determine history_disabled
    receive_group = gift.group_reserved_on
    if not receive_group and group_id:
        try:
            receive_group = Group.objects.get(id=int(group_id))
        except Group.DoesNotExist:
            return JsonResponse({"success": False, "error": _("GROUP_NOT_FOUND")}, status=404)
        except (ValueError, TypeError):
            return JsonResponse({"success": False, "error": _("Invalid group ID.")}, status=400)
    history_disabled = receive_group is not None and not receive_group.show_history

    if not confirm:
        if history_disabled:
            context = {
                "gift": gift,
                "group_id": group_id,
                "history_disabled": True,
                "reservations": reservations,
                "possible_givers": [],
            }
            return render(request, "gifts/includes/_mark_received_content.html", context)

        if group_id:
            try:
                givers_group = Group.objects.get(id=int(group_id))
                possible_givers = givers_group.members.exclude(id=request.user.id)
            except (Group.DoesNotExist, ValueError, TypeError):
                possible_givers = User.objects.none()
        elif gift.visible_in.exists():
            possible_givers = (
                User.objects.filter(gift_groups__visible_gifts=gift).exclude(id=request.user.id).distinct()
            )
        else:
            possible_givers = (
                User.objects.filter(gift_groups__members=request.user).exclude(id=request.user.id).distinct()
            )
        context = {
            "gift": gift,
            "reservations": reservations,
            "possible_givers": possible_givers,
            "group_id": group_id,
        }
        return render(request, "gifts/includes/_mark_received_content.html", context)

    if history_disabled:
        gift.delete()
        return JsonResponse({"success": True})

    if not reservations:
        giver_ids = data.get("giver_ids", [])
        valid_giver_ids = set(
            User.objects.filter(gift_groups__members=request.user)
            .exclude(id=request.user.id)
            .values_list("id", flat=True)
        )
        exclusive = len(giver_ids) == 1
        for giver_id in giver_ids:
            if giver_id in valid_giver_ids:
                giver = User.objects.get(id=giver_id)
                Reservation.objects.get_or_create(gift=gift, reserver=giver, defaults={"exclusivity": exclusive})

    if group_id and not gift.group_reserved_on_id:
        try:
            gift.group_reserved_on = Group.objects.get(id=int(group_id))
        except (Group.DoesNotExist, ValueError, TypeError):
            return JsonResponse({"success": False, "error": _("GROUP_NOT_FOUND")}, status=400)

    gift.offered = True
    gift.offered_at = timezone.now()
    gift.save()

    return JsonResponse({"success": True})
