import datetime
import json
import random
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.core.management import call_command
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .forms import GroupForm, LocalUserCreationForm, UserProfileForm
from .models import Gift, Group, Reservation, User


@login_required
def profile(request):
    if request.method == 'POST':
        old_email = request.user.email
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)

            if user.email != old_email:
                user.is_verified = False
                user.save()
                send_verification_email(request, user)
                messages.success(request, _("Profile updated! Please verify your new email address."))
                return redirect('verify_email_sent')

            form.save()
            messages.success(request, _("Your profile has been updated!"))
            return redirect('profile')
    else:
        form = UserProfileForm(instance=request.user)

    return render(request, 'gifts/profile.html', {'form': form})


def welcome(request):
    if request.user.is_authenticated:
        if request.user.is_verified:
            return redirect('dashboard')
        else:
            return redirect('verify_email_sent')
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
    if request.user.is_authenticated:
        return redirect('dashboard')
    call_command('cleanup_unverified_users')

    if request.method == 'POST':
        form = LocalUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()

            login(request, user, backend='gifts.backends.CaseInsensitiveModelBackend')
            send_verification_email(request, user)

            return redirect('dashboard')
    else:
        form = LocalUserCreationForm()
    return render(request, 'registration/register.html', {'form': form})


def send_verification_email(request, user):
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    domain = get_current_site(request).domain

    link = f"http://{domain}{reverse('verify_email_confirm', kwargs={'uidb64': uid, 'token': token})}"

    context = {'nickname': user.nickname, 'verification_link': link}
    subject = _("Verify your email address on Nos Cadeaux!")
    message_txt = render_to_string('emails/verify_email.txt', context)
    message_html = render_to_string('emails/verify_email.html', context)

    send_mail(subject, message_txt, None, [user.email], html_message=message_html)


def verify_email_sent(request):
    if not request.user.is_authenticated:
        return redirect('welcome')
    if request.user.is_verified:
        return redirect('dashboard')
    return render(request, 'gifts/verify_email_sent.html')


def verify_email_confirm(request, uidb64, token):
    # call_command('cleanup_unverified_users')

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_verified = True
        user.save()
        messages.success(request, _("Your account is now verified !"))
        return redirect('dashboard')
    else:
        messages.error(request, _("The verification link is invalid"))
        return redirect('welcome')


@login_required
def resend_verification(request):
    if not request.user.is_authenticated:
        return redirect('welcome')
    if request.user.is_verified:
        messages.success(request, _("Your email is already verified."))
        return redirect('dashboard')
    send_verification_email(request, request.user)
    messages.success(request, _("A new verification email has been sent."))
    return redirect('verify_email_sent')


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
@require_POST
def edit_group(request, group_id):
    group = get_object_or_404(Group, id=group_id, )
    new_name = request.POST.get('name', '').strip()
    if new_name:
        group.name = new_name
        group.save()
        messages.success(request, _("Group name updated !"))
    return redirect('group_detail', group_id=group.id)


@login_required
@require_POST
def regenerate_group_token(request, group_id):
    group = get_object_or_404(Group, id=group_id, )
    group.invite_token = ""  # Will be regenerated in save()
    group.save()
    messages.success(request, _("New invitation code generated !"))
    return redirect('group_detail', group_id=group.id)


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
        all_reservations = Reservation.objects.filter(gift__in=all_gifts).select_related('reserver')

        other_members = []
        if from_group_id:

            group = get_object_or_404(Group, id=from_group_id)

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

    return render(request, "gifts/view_list.html", {
        "user": target_user,
        "gifts": gifts,
        "surprises": surprises,
        "is_owner": is_owner,
        "from_group_id": from_group_id,
        "user_groups": user_groups,
        "is_subscribed": request.user.subscriptions.filter(id=target_user.id).exists() if not is_owner else False,
    })


@login_required
@require_POST
def toggle_subscription(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    if target_user == request.user:
        return HttpResponseForbidden(_("You cannot subscribe to yourself"))

    if not Group.objects.filter(members=request.user).filter(members=target_user).exists():
        return HttpResponseForbidden(_("You don't have access to this list"))

    if request.user.subscriptions.filter(id=target_user.id).exists():
        request.user.subscriptions.remove(target_user)
        messages.success(request, _("You are no longer subscribed to %(name)s's list") % {'name': target_user.nickname})
    else:
        request.user.subscriptions.add(target_user)
        messages.success(request, _("You are now subscribed to %(name)s's list") % {'name': target_user.nickname})

    return redirect('view_list', user_id=user_id)


@login_required
def unsubscribe_token(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        target_user = get_object_or_404(User, id=uid)

        if request.user.subscriptions.filter(id=target_user.id).exists():
            request.user.subscriptions.remove(target_user)
            messages.success(request,
                             _("You are no longer subscribed to %(name)s's list") % {'name': target_user.nickname})

        return redirect('view_list', user_id=target_user.id)
    except (TypeError, ValueError, OverflowError):
        messages.error(request, _("The unsubscription link is invalid"))
        return redirect('dashboard')


@login_required
@require_POST
def add_gift(request, owner_id):
    owner = get_object_or_404(User, id=owner_id)

    # Security check: can only add to own list or list of someone in common group
    if (owner != request.user
            and not Group.objects.filter(members=request.user).filter(members=owner).exists()):
        return HttpResponseForbidden(_("You don't have access to this list"))

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
            valid_groups = (Group.objects
                            .filter(id__in=group_ids, members=request.user))
            gift.visible_in.set(valid_groups)

        # Send notification to all subscribers of the owner
        if owner == request.user:
            subscribers = owner.subscribers.all()
            if subscribers.exists():
                protocol = 'https' if request.is_secure() else 'http'
                domain = get_current_site(request).domain
                list_url = f"{protocol}://{domain}{reverse('view_list', args=[owner.id])}"

                for subscriber in subscribers:
                    if Group.objects.filter(members=owner).filter(members=subscriber).exists():

                        gift_groups = gift.visible_in.all()
                        if (gift_groups.exists() and
                                not gift_groups.filter(members=subscriber).exists()):
                            continue

                        uid = urlsafe_base64_encode(force_bytes(owner.pk))
                        token = default_token_generator.make_token(subscriber)
                        unsubscribe_url = f"{protocol}://{domain}{reverse('unsubscribe_token', args=[uid, token])}"

                        context = {
                            'subscriber': subscriber,
                            'owner': owner,
                            'gift': gift,
                            'list_url': list_url,
                            'unsubscribe_url': unsubscribe_url,
                        }

                        subject = _("New gift on %(name)s's list!") % {'name': owner.nickname}
                        html_message = render_to_string('emails/gift_added_notification.html', context)
                        plain_message = render_to_string('emails/gift_added_notification.txt', context)

                        send_mail(
                            subject,
                            plain_message,
                            settings.DEFAULT_FROM_EMAIL,
                            [subscriber.email],
                            html_message=html_message
                        )
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
        return JsonResponse({"error": "Method " + request.method + " not authorized"}, status=405)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"success": False, "error": "ValueError: Please provide valid data"}, status=400)
    except TypeError:
        return JsonResponse({"success": False, "error": "TypeError: Please provide valid data"}, status=400)

    try:
        exclusivity = data.get('exclusivity')
        user_id = data.get('user_id')
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Unable to find exclusivity"}, status=400)

    gift = get_object_or_404(Gift, id=gift_id)
    user = get_object_or_404(User, id=user_id)

    if gift.owner == request.user:
        return HttpResponseForbidden("Impossible on your own list")

    # Common group verification
    if not Group.objects.filter(members=request.user).filter(members=gift.owner).exists():
        return HttpResponseForbidden(_("You don't have access to this list"))

    if Reservation.objects.filter(gift=gift, reserver=user).exists():
        return JsonResponse({"success": False, "error": "This person already joined this gift"}, status=409)

    if Reservation.objects.filter(gift=gift, exclusivity=True).exists():
        return JsonResponse({"success": False, "error": "Someone else reserved exclusively this gift"}, status=409)

    Reservation.objects.create(gift=gift, reserver=user, exclusivity=exclusivity)

    group_id = data.get('group_id')
    group = Group.objects.get(id=group_id)

    if not group.members.filter(id=gift.owner.id):
        return HttpResponseForbidden(_("You don't have access to this list"))

    gift.group_reserved_on = group
    gift.save()

    reservations = Reservation.objects.filter(gift=gift).order_by('id')

    user_res = next((r for r in reservations if r.reserver_id == request.user.id), None)

    user_already_participating = (r.reserver.id for r in reservations)

    group = get_object_or_404(Group, id=group_id)
    other_members = (group.members
                     .exclude(id__in=[request.user.id, gift.owner.id])
                     .exclude(id__in=user_already_participating))

    context = {
        'item': {
            "current_user": request.user,
            'gift': gift,
            'reservations': reservations,
            'user_reservation': user_res,
            "other_non_participant": other_members,
            "group_id": group_id
        }
    }

    return render(request, 'gifts/includes/_reserve_modal_content.html', context)


@login_required
def modify_reservation(request: HttpRequest, gift_id: int):
    if request.method != "POST":
        return JsonResponse({"error": "Method " + request.method + " not authorized"}, status=405)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"success": False, "error": "ValueError: Please provide valid data"}, status=400)
    except TypeError:
        return JsonResponse({"success": False, "error": "TypeError: Please provide valid data"}, status=400)

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

    reservations = Reservation.objects.filter(gift=gift).order_by('id')

    user_res = next((r for r in reservations if r.reserver_id == request.user.id), None)

    group_id = data.get('group_id')
    group = get_object_or_404(Group, id=group_id)
    other_members = group.members.exclude(id__in=[request.user.id, gift.owner.id])

    context = {
        "item": {
            "current_user": request.user,
            "gift": gift,
            "reservations": reservations,
            "user_reservation": user_res,
            "other_non_participant": other_members,
            "group_id": group_id
        }
    }

    return render(request, 'gifts/includes/_reserve_modal_content.html', context)


@login_required
@require_POST
def delete_reservation(request, gift_id):
    if request.method != "POST":
        return JsonResponse({"error": "Method " + request.method + " not authorized"}, status=405)

    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({"success": False, "error": "ValueError: Please provide valid data"}, status=400)
    except TypeError:
        return JsonResponse({"success": False, "error": "TypeError: Please provide valid data"}, status=400)

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

    reservations = Reservation.objects.filter(gift=gift).order_by('id')

    user_res = next((r for r in reservations if r.reserver_id == request.user.id), None)

    group_id = data.get('group_id')
    group = get_object_or_404(Group, id=group_id)
    other_members = group.members.exclude(id__in=[request.user.id, gift.owner.id])

    context = {
        'item': {
            'current_user': request.user,
            'gift': gift,
            'reservations': reservations,
            'user_reservation': user_res,
            "other_non_participant": other_members,
            "group_id": group_id
        }
    }

    return render(request, 'gifts/includes/_reserve_modal_content.html', context)
