import uuid
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from gifts.demo import has_same_demo_scope
from gifts.models import (
    Gift,
    GiftComment,
    GiftTag,
    Group,
    Reservation,
    SharedGiftPublication,
    SharedList,
    SharedListMembership,
    User,
)

PERMISSION_DENIED = _("You do not have permission to perform this action.")


def _active_member_list(list_id, user):
    return get_object_or_404(
        SharedList.objects.prefetch_related("members"),
        id=list_id,
        deleted_at__isnull=True,
        members=user,
    )


def _selected_tags(request):
    slugs = set(request.POST.getlist("tags"))
    if not slugs:
        return GiftTag.objects.none()
    if not slugs.issubset(set(GiftTag.Slug.values)):
        return None
    tags = GiftTag.objects.filter(slug__in=slugs)
    return tags if tags.count() == len(slugs) else None


def _selected_visibility(request, user):
    values = request.POST.getlist("visible_in")
    if not values:
        return Group.objects.none()
    try:
        ids = {int(value) for value in values}
    except (TypeError, ValueError):
        return None
    groups = user.gift_groups.filter(is_demo=user.is_demo, id__in=ids)
    return groups if groups.count() == len(ids) else None


def _send_template_email(subject, template_name, context, recipient):
    if not recipient:
        return
    send_mail(
        subject,
        render_to_string(f"emails/{template_name}.txt", context),
        settings.DEFAULT_FROM_EMAIL,
        [recipient],
        html_message=render_to_string(f"emails/{template_name}.html", context),
    )


@login_required
@require_POST
def create_shared_list(request):
    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, _("A list name is required."))
        return redirect("dashboard")
    shared_list = SharedList.objects.create(name=name, is_demo=request.user.is_demo)
    SharedListMembership.objects.create(shared_list=shared_list, user=request.user)
    messages.success(request, _("Shared list created."))
    return redirect("shared_list_detail", list_id=shared_list.id)


@login_required
@require_POST
def rename_shared_list(request, list_id):
    shared_list = _active_member_list(list_id, request.user)
    name = request.POST.get("name", "").strip()
    if not name:
        messages.error(request, _("A list name is required."))
    else:
        shared_list.name = name
        shared_list.save(update_fields=["name"])
        messages.success(request, _("Shared list renamed."))
    return redirect("shared_list_detail", list_id=list_id)


def _shared_list_group_context(request, shared_list):
    from_group_id = request.GET.get("from_group")
    if not from_group_id:
        return None, None, None
    group = get_object_or_404(Group, id=from_group_id, members=request.user)
    publication_query = SharedGiftPublication.objects.filter(
        gift__shared_list=shared_list,
        group=group,
        published_by__in=shared_list.members.all(),
    ).select_related("published_by")
    published_by_id = request.GET.get("published_by")
    if published_by_id:
        publication = get_object_or_404(publication_query, published_by_id=published_by_id)
    else:
        publication = publication_query.order_by("id").first()
    if publication is None:
        return None, None, HttpResponseForbidden(PERMISSION_DENIED)
    return group, publication.published_by, None


def _shared_gifts(shared_list, group, published_by):
    gifts_qs = shared_list.gifts.filter(offered=False, is_draft=False, event_list__isnull=True)
    if group:
        gifts_qs = gifts_qs.filter(
            shared_publications__group=group,
            shared_publications__published_by=published_by,
        ).distinct()
    gifts_qs = (
        gifts_qs.select_related("created_by")
        .prefetch_related("tags", "shared_publications__group", "shared_publications__published_by")
        .order_by("created_at", "id")
    )
    return gifts_qs


def _manager_gift_items(gifts, user):
    gift_items = []
    for gift in gifts:
        publications_by_member = defaultdict(list)
        my_publication_ids = set()
        for publication in gift.shared_publications.all():
            publications_by_member[publication.published_by].append(publication.group)
            if publication.published_by_id == user.id:
                my_publication_ids.add(publication.group_id)
        gift_items.append(
            {
                "gift": gift,
                "reservation_state": None,
                "comments": [],
                "my_publication_ids": my_publication_ids,
                "publication_groups": [
                    {"member": member, "groups": groups} for member, groups in publications_by_member.items()
                ],
            }
        )
    return gift_items


def _visitor_gift_items(request, gifts, shared_list, group):
    from gifts.views import _gift_item

    reservations_by_gift = defaultdict(list)
    for reservation in Reservation.objects.filter(gift__in=gifts).select_related("reserver"):
        reservations_by_gift[reservation.gift_id].append(reservation)
    excluded_ids = list(shared_list.members.values_list("id", flat=True)) + [request.user.id]
    other_members = group.members.exclude(id__in=excluded_ids)
    return [_gift_item(request, gift, reservations_by_gift[gift.id], str(group.id), other_members) for gift in gifts]


def _shared_list_candidates(request, shared_list):
    return (
        User.objects.filter(
            gift_groups__members=request.user,
            is_active=True,
            is_managed=False,
            is_demo=request.user.is_demo,
        )
        .exclude(id__in=shared_list.members.values_list("id", flat=True))
        .distinct()
        .order_by("nickname", "email")
    )


@login_required
@require_GET
def shared_list_detail(request, list_id):
    shared_list = get_object_or_404(
        SharedList.objects.prefetch_related("members"),
        id=list_id,
        deleted_at__isnull=True,
    )
    if not has_same_demo_scope(request.user, shared_list):
        return HttpResponseForbidden(PERMISSION_DENIED)

    is_manager = shared_list.members.filter(id=request.user.id).exists()
    group, published_by, group_error = _shared_list_group_context(request, shared_list)
    if group_error:
        return group_error
    if not is_manager and not group:
        return HttpResponseForbidden(PERMISSION_DENIED)

    gifts = _shared_gifts(shared_list, group, published_by)
    gift_items = (
        _manager_gift_items(gifts, request.user)
        if is_manager
        else _visitor_gift_items(request, gifts, shared_list, group)
    )
    is_management_view = is_manager and not group
    my_groups = request.user.gift_groups.filter(is_demo=request.user.is_demo).order_by("name")
    candidates = _shared_list_candidates(request, shared_list) if is_management_view else User.objects.none()

    return render(
        request,
        "shared_lists/detail.html",
        {
            "shared_list": shared_list,
            "gift_items": gift_items,
            "is_manager": is_manager,
            "is_management_view": is_management_view,
            "group": group,
            "published_by": published_by,
            "from_group_id": str(group.id) if group else "",
            "my_groups": my_groups if is_management_view else Group.objects.none(),
            "candidate_members": candidates,
            "available_tags": GiftTag.objects.all(),
            "shared_lists_for_move": request.user.shared_lists.filter(deleted_at__isnull=True),
        },
    )


@login_required
@require_POST
def add_shared_gift(request, list_id):
    shared_list = _active_member_list(list_id, request.user)
    title = request.POST.get("title", "").strip()
    tags = _selected_tags(request)
    visible_in = _selected_visibility(request, request.user)
    if not title or tags is None or visible_in is None:
        messages.error(request, _("Invalid wish data."))
        return redirect("shared_list_detail", list_id=list_id)
    gift = Gift.objects.create(
        owner=request.user,  # Compatibility anchor; shared_list is the functional owner.
        shared_list=shared_list,
        created_by=request.user,
        title=title,
        description=request.POST.get("description", "").strip(),
        url=request.POST.get("url", "").strip(),
    )
    gift.tags.set(tags)
    SharedGiftPublication.objects.bulk_create(
        [SharedGiftPublication(gift=gift, group=group, published_by=request.user) for group in visible_in]
    )
    messages.success(request, _("Wish added."))
    return redirect("shared_list_detail", list_id=list_id)


@login_required
@require_POST
def edit_shared_gift(request, list_id, gift_id):
    shared_list = _active_member_list(list_id, request.user)
    gift = get_object_or_404(Gift, id=gift_id, shared_list=shared_list, offered=False)
    title = request.POST.get("title", "").strip()
    tags = _selected_tags(request)
    visible_in = _selected_visibility(request, request.user)
    if not title or tags is None or visible_in is None:
        messages.error(request, _("Invalid wish data."))
        return redirect("shared_list_detail", list_id=list_id)
    gift.title = title
    gift.description = request.POST.get("description", "").strip()
    gift.url = request.POST.get("url", "").strip()
    gift.save(update_fields=["title", "description", "url"])
    gift.tags.set(tags)
    SharedGiftPublication.objects.filter(gift=gift, published_by=request.user).delete()
    SharedGiftPublication.objects.bulk_create(
        [SharedGiftPublication(gift=gift, group=group, published_by=request.user) for group in visible_in]
    )
    messages.success(request, _("Wish updated."))
    return redirect("shared_list_detail", list_id=list_id)


@login_required
@require_POST
def delete_shared_gift(request, list_id, gift_id):
    shared_list = _active_member_list(list_id, request.user)
    get_object_or_404(Gift, id=gift_id, shared_list=shared_list).delete()
    messages.success(request, _("Wish deleted."))
    return redirect("shared_list_detail", list_id=list_id)


@login_required
@require_POST
def add_shared_list_member(request, list_id):
    shared_list = _active_member_list(list_id, request.user)
    candidate = get_object_or_404(
        User,
        id=request.POST.get("user_id"),
        is_active=True,
        is_managed=False,
        is_demo=request.user.is_demo,
    )
    if not Group.objects.filter(members=request.user).filter(members=candidate).exists():
        return HttpResponseForbidden(PERMISSION_DENIED)
    with transaction.atomic():
        SharedListMembership.objects.get_or_create(shared_list=shared_list, user=candidate)
        affected_gifts = list(Gift.objects.filter(shared_list=shared_list, reservation__reserver=candidate).distinct())
        Reservation.objects.filter(gift__shared_list=shared_list, reserver=candidate).delete()
        for gift in affected_gifts:
            if not gift.reservation.exists():
                gift.group_reserved_on = None
                gift.save(update_fields=["group_reserved_on"])
    messages.success(request, _("Member added."))
    return redirect("shared_list_detail", list_id=list_id)


def _transfer_to_personal_list(shared_list, remaining_user):
    gifts = shared_list.gifts.prefetch_related("shared_publications__group")
    for gift in gifts:
        visible_groups = [
            publication.group
            for publication in gift.shared_publications.all()
            if publication.published_by_id == remaining_user.id
        ]
        gift.shared_publications.all().delete()
        gift.owner = remaining_user
        gift.shared_list = None
        gift.group_reserved_on = None
        gift.save(update_fields=["owner", "shared_list", "group_reserved_on"])
        gift.visible_in.set(visible_groups)
    shared_list.delete()


@login_required
@require_POST
def remove_shared_list_member(request, list_id, user_id):
    shared_list = _active_member_list(list_id, request.user)
    member = get_object_or_404(shared_list.members.all(), id=user_id)
    members = list(shared_list.members.all())
    if len(members) <= 2:
        resolution = request.POST.get("resolution")
        if resolution == "delete":
            return _soft_delete(request, shared_list)
        if resolution != "transfer":
            messages.error(request, _("Choose whether to transfer the wishes or delete the list."))
            return redirect("shared_list_detail", list_id=list_id)
        remaining = next(user for user in members if user.id != member.id)
        with transaction.atomic():
            _transfer_to_personal_list(shared_list, remaining)
        messages.success(
            request,
            _("The wishes were transferred to %(name)s's personal list.") % {"name": remaining.nickname},
        )
        return redirect("dashboard")

    SharedGiftPublication.objects.filter(gift__shared_list=shared_list, published_by=member).delete()
    SharedListMembership.objects.filter(shared_list=shared_list, user=member).delete()
    transaction.on_commit(
        lambda: _send_template_email(
            _("You were removed from a shared list"),
            "shared_list_member_removed",
            {"member": member, "shared_list": shared_list},
            member.email,
        )
    )
    messages.success(request, _("Member removed."))
    return redirect("shared_list_detail", list_id=list_id)


@login_required
@require_POST
def move_gift_to_shared_list(request, gift_id, list_id):
    shared_list = _active_member_list(list_id, request.user)
    with transaction.atomic():
        gift = get_object_or_404(
            Gift.objects.select_for_update(),
            id=gift_id,
            owner=request.user,
            shared_list__isnull=True,
            event_list__isnull=True,
            offered=False,
        )
        reservations = list(Reservation.objects.filter(gift=gift).select_related("reserver"))
        selected_groups = list(gift.visible_in.filter(members=request.user))
        if not selected_groups:
            selected_groups = list(request.user.gift_groups.filter(is_demo=request.user.is_demo))
        recipients = sorted({reservation.reserver.email for reservation in reservations if reservation.reserver.email})
        gift_title = gift.title
        Reservation.objects.filter(gift=gift).delete()
        GiftComment.objects.filter(gift=gift).delete()
        gift.expense_split.clear()
        gift.shared_list = shared_list
        gift.group_reserved_on = None
        gift.actual_cost = None
        gift.save(update_fields=["shared_list", "group_reserved_on", "actual_cost"])
        gift.visible_in.clear()
        SharedGiftPublication.objects.bulk_create(
            [SharedGiftPublication(gift=gift, group=group, published_by=request.user) for group in selected_groups]
        )

        if recipients:
            context = {"gift_title": gift_title, "shared_list": shared_list}

            def notify_reservers():
                for recipient in recipients:
                    _send_template_email(
                        _("A reservation was cancelled"),
                        "shared_gift_reservation_cancelled",
                        context,
                        recipient,
                    )

            transaction.on_commit(notify_reservers)

    messages.success(request, _("Wish moved to the shared list."))
    return redirect("shared_list_detail", list_id=list_id)


def _soft_delete(request, shared_list):
    shared_list.deleted_at = timezone.now()
    shared_list.restore_token = uuid.uuid4()
    shared_list.save(update_fields=["deleted_at", "restore_token"])
    restore_url = request.build_absolute_uri(
        reverse("restore_shared_list", args=[shared_list.id, shared_list.restore_token])
    )
    members = list(shared_list.members.exclude(email=""))

    def notify_members():
        for member in members:
            _send_template_email(
                _("Shared list deleted — restoration available for 48 hours"),
                "shared_list_deleted",
                {"member": member, "shared_list": shared_list, "restore_url": restore_url},
                member.email,
            )

    transaction.on_commit(notify_members)
    messages.success(request, _("The list can be restored for 48 hours."))
    return redirect("dashboard")


@login_required
@require_POST
def delete_shared_list(request, list_id):
    return _soft_delete(request, _active_member_list(list_id, request.user))


@login_required
def restore_shared_list(request, list_id, token):
    shared_list = get_object_or_404(SharedList, id=list_id, restore_token=token, members=request.user)
    if not shared_list.deleted_at:
        return redirect("shared_list_detail", list_id=list_id)
    if shared_list.deleted_at < timezone.now() - timedelta(hours=48):
        return render(request, "shared_lists/restore_expired.html", status=410)
    if request.method == "POST":
        shared_list.deleted_at = None
        shared_list.save(update_fields=["deleted_at"])
        messages.success(request, _("Shared list restored."))
        return redirect("shared_list_detail", list_id=list_id)
    return render(request, "shared_lists/restore.html", {"shared_list": shared_list, "token": token})
