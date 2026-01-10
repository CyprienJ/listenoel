import datetime
import random

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, update_session_auth_hash, logout as auth_logout
from django.db.models import QuerySet, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden, HttpRequest
from django.db import transaction, IntegrityError
from django.views.decorators.http import require_POST
from django.utils.translation import gettext as _

from .forms import LocalUserCreationForm, GroupForm, UserProfileForm
from .models import User, Gift, Reservation, Group


@login_required
def profile(request):
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("Your profile has been updated!"))
            return redirect('profile')
    else:
        form = UserProfileForm(instance=request.user)

    return render(request, 'gifts/profile.html', {'form': form})

def welcome(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'gifts/welcome.html')

@login_required
@require_POST
def delete_account(request):
    user = request.user
    auth_logout(request)
    user.delete()
    messages.success(request, _("Your account has been successfully deleted."))
    return redirect('welcome')

def register(request):
    if request.method == 'POST':
        form = LocalUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()

            # subject = _("Welcome to Nos Cadeaux!")
            # message = _(
            #     "Hello %(nickname)s,\n\nYour account has been successfully created. Ready to prepare wonderful surprises?") % {
            #               'nickname': user.nickname}
            # send_mail(
            #     subject,
            #     message,
            #     'noreply@noscadeaux.com',
            #     [user.email],
            #     fail_silently=True,
            # )
            # messages.success(request,
            #                  _("Welcome! A confirmation email has been sent to %(email)s.") % {'email': user.email})

            login(request, user, backend='gifts.backends.CaseInsensitiveModelBackend')
            return redirect('dashboard')
    else:
        form = LocalUserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


@login_required
def dashboard(request):
    user_groups = request.user.gift_groups.all()

    current_emoji_set = emojis()

    return render(request, "gifts/dashboard.html", {
        "user_groups": user_groups,
        "greeting_emoji": random.choice(current_emoji_set),
        "rain_emojis": current_emoji_set,
    })


def emojis():
    christmas_emojis = ["🎄", "🎁", "🎅", "🤶", "🧑‍🎄", "⛄", "✨", "🌟", "🔔", "🦌"]
    gift_emojis = ["🎁", "🎈", "🎊", "🎉", "✨", "🍰", "🥳", "🎀"]
    if datetime.date.today().month == 12 and datetime.date.today().day <= 25:
        return christmas_emojis
    else:
        return gift_emojis


@login_required
@require_POST
def create_group(request):
    form = GroupForm(request.POST)
    if form.is_valid():
        group = form.save(commit=False)
        group.created_by = request.user
        group.save()
        group.members.add(request.user)
        msg = _("Group '%(name)s' created ! Share this code: %(token)s") % {
            'name': group.name,
            'token': group.invite_token
        }
        messages.success(request, msg)
    else:
        for error in form.errors.values():
            messages.error(request, error.as_text())

    return redirect('dashboard')


@login_required
@require_POST
def join_group(request):
    token = request.POST.get('invite_token', '').strip().upper()
    if not token:
        messages.error(request, _("Please enter a group code."))
        return redirect('dashboard')

    group = Group.objects.filter(invite_token=token).first()

    if group:
        if request.user in group.members.all():
            messages.info(request, _("You are already a member of the group '%s'.") % group.name)
        else:
            group.members.add(request.user)
            messages.success(request, _("You have joined the group '%s'!") % group.name)
        return redirect('group_detail', group_id=group.id)
    else:
        messages.error(request, _("No group found with this code."))

    return redirect('dashboard')


@login_required
def group_detail(request, group_id):
    group = Group.objects.filter(id=group_id).first()

    if not group:
        return render(request, 'gifts/group_not_found.html', status=404)

    if request.user not in group.members.all():
        return HttpResponseForbidden(_("You are not a member of this group."))

    return render(request, 'gifts/group_detail.html', {'group': group})


@login_required
@require_POST
def leave_group(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    if request.user in group.members.all():
        group.members.remove(request.user)
        messages.success(request, _("You have left the group '%s'.") % group.name)
    if group.members.count() == 0:
        group.delete()
    return redirect('dashboard')


@login_required
def view_list(request: HttpRequest, user_id: int):
    # the user whose list we're viewing
    target_user = User.objects.filter(id=user_id).first()

    if not target_user:
        return render(request, "gifts/user_not_found.html", status=404)

    is_owner = (request.user.id == target_user.id)

    if not is_owner:
        common_groups = Group.objects.filter(members=request.user).filter(members=target_user).exists()
        if not common_groups:
            return render(request, "gifts/user_not_found.html", status=403)

    all_gifts_query: QuerySet[Gift] = Gift.objects.filter(owner=target_user).order_by("created_at")

    from_group_id = request.GET.get('from_group')
    if from_group_id and not is_owner:
        all_gifts_query = all_gifts_query.filter(
            Q(visible_in__isnull=True) | Q(visible_in__id=from_group_id)
        ).distinct()

    all_gifts = all_gifts_query.prefetch_related('visible_in')
    user_groups = request.user.gift_groups.all()

    gifts: list = []
    surprises: list = []

    if is_owner:
        # Someone views their own list -> don't show surprises nor who reserved a gift
        for g in all_gifts:
            if g.created_by == g.owner:
                gifts.append({"gift": g, "is_reserved": None})
    else:
        reservations = {r.gift.id: r for r in Reservation.objects.filter(gift__in=all_gifts)}
        user_groups_ids = set(request.user.gift_groups.values_list('id', flat=True))

        for g in all_gifts:
            r = reservations.get(g.id)

            show_reserver_name = False

            if r:
                reserver_groups_ids = set(r.reserver.gift_groups.values_list('id', flat=True))
                if user_groups_ids & reserver_groups_ids:
                    show_reserver_name = True

            item = {
                "gift": g,
                "is_reserved": bool(r),
                "reserved_by": r.reserver if r else None,
                "show_reserver_name": show_reserver_name
            }
            if g.created_by == g.owner:
                gifts.append(item)
            else:
                surprises.append(item)

    return render(request, "gifts/view_list.html", {
        "user": target_user,
        "gifts": gifts,
        "surprises": surprises,
        "is_owner": is_owner,
        "from_group_id": from_group_id,
        "user_groups": user_groups,
    })


@login_required
@transaction.atomic
def reserve_gift(request: HttpRequest, gift_id: int):
    gift = get_object_or_404(Gift, id=gift_id)

    if gift.owner == request.user:
        return HttpResponseForbidden(_("Impossible on your own list"))

    try:
        Reservation.objects.create(gift=gift, reserver=request.user)
    except IntegrityError:
        return JsonResponse({"success": False, "error": _("This gift is already taken")}, status=409)

    return JsonResponse({"success": True})


@login_required
@require_POST
def unreserve_gift(request, gift_id):
    reservation = get_object_or_404(Reservation, gift_id=gift_id, reserver=request.user)
    owner_id = reservation.gift.owner.id
    reservation.delete()
    return redirect("view_list", user_id=owner_id)


@login_required
@require_POST
def add_gift(request, owner_id):
    owner = get_object_or_404(User, id=owner_id)
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
            gift.visible_in.set(group_ids)
    return redirect("view_list", user_id=owner.id)

@login_required
@require_POST
def delete_gift(request, gift_id):
    gift = get_object_or_404(Gift, id=gift_id, created_by=request.user)
    owner_id = gift.owner.id
    gift.delete()
    return redirect("view_list", user_id=owner_id)


@login_required
@require_POST
def edit_gift(request: HttpRequest, gift_id: int):
    gift = get_object_or_404(Gift, id=gift_id)

    title = request.POST.get("title", "").strip()

    if title:
        gift.title = title
        gift.description = request.POST.get("description", "").strip()
        gift.url = request.POST.get("url", "").strip()
        gift.save()

        group_ids = request.POST.getlist("visible_in")
        gift.visible_in.set(group_ids)

    return redirect("view_list", user_id=gift.owner.id)


# ... existing code ...
@login_required
def change_password(request):
    if request.method == 'POST':
        old_password = request.POST.get('old_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        if not request.user.check_password(old_password):
            messages.error(request, _("Old password incorrect"))
        elif new_password != confirm_password:
            messages.error(request, _("The new passwords don't match."))
        elif len(new_password) < 8:
            messages.error(request, _("New password is too short."))
        else:
            request.user.set_password(new_password)
            request.user.save()
            update_session_auth_hash(request, request.user)
            messages.success(request, _("Password successfully updated !"))
            return redirect('dashboard')

    return render(request, 'gifts/change_password.html')
