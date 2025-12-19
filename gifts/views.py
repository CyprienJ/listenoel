import random
import re

from django.db.models import QuerySet
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden, HttpRequest
from django.db import transaction, IntegrityError
from django.views.decorators.http import require_POST

from .models import User, Gift, Reservation, Group

# Fourteen days
SESSION_EXPIRY_DURATION = 60 * 60 * 24 * 14

def get_current_user(request: HttpRequest):
    uid = request.session.get("user_id")
    if not uid:
        return None
    return User.objects.filter(id=uid).first()

def dashboard(request: HttpRequest):
    current: User = get_current_user(request)
    if not current:
        return redirect("choose_group")

    users: QuerySet[User] = (User.objects.filter(group=current.group)
                               .order_by("pseudo")
                                  .exclude(id=current.id))

    christmas_emojis = [
        "🎄", "🎁", "🎅", "🤶", "🧑‍🎄", "⛄", "☃️", "❄️", "🌨️", "✨", "🌟", "⭐", "🔔", "🕯️", "🍫", "🦌", "🛷", "🎶", "🎉", "🎊",
    ]
    greeting_emoji: str = random.choice(christmas_emojis)

    return render(request, "gifts/dashboard.html", {
        "current": current,
        "users": users,
        "greeting_emoji": greeting_emoji,
    })


def view_list(request: HttpRequest, user_id: int):
    # the current user, if any
    current: User = get_current_user(request)

    # the user whose list we're viewing'
    user: User = get_object_or_404(User, id=user_id)

    all_gifts: QuerySet[Gift] = Gift.objects.filter(owner=user).order_by("created_at")

    gifts: list = []
    surprises: list = []

    if current and current.id == user.id:
        # Someone views their own list -> don't show surprises nor who reserved a gift
        for g in all_gifts:
            if g.created_by.id == g.owner.id:
                gifts.append({
                    "gift": g,
                    "is_reserved": None,
                    "reserved_by": None
                })
    else:
        reservations = {r.gift.id: r for r in Reservation.objects.filter(gift__in=all_gifts)}
        for g in all_gifts:
            r = reservations.get(g.id)
            if g.created_by.id == g.owner.id:
                gifts.append({
                    "gift": g,
                    "is_reserved": bool(r),
                    "reserved_by": r.reserver if r else None
                })
            else :
                surprises.append({
                    "gift": g,
                    "is_reserved": bool(r),
                    "reserved_by": r.reserver if r else None
                })


    return render(request, "gifts/view_list.html", {
        "user": user,
        "gifts": gifts,
        "presence_gift": len(gifts) > 0,
        "surprises": surprises,
        "presence_surprises": len(surprises) > 0,
        "current": current
    })


@transaction.atomic
def reserve_gift(request: HttpRequest, gift_id: int):
    current: User = get_current_user(request)
    if not current:
        redirect("choose_user")

    gift = get_object_or_404(Gift, id=gift_id)

    if gift.owner_id == current.id:
        return HttpResponseForbidden("Impossible sur votre propre liste")

    try:
        Reservation.objects.create(gift=gift, reserver=current)
    except IntegrityError:
        return JsonResponse({"success": False, "error": "Déjà réservé"}, status=409)

    return JsonResponse({"success": True})

def choose_group(request):
    current = get_current_user(request)
    if current:
        return redirect("dashboard")
    groups = Group.objects.all().order_by("name")
    return render(request, "gifts/choose_group.html", {"groups": groups})


def choose_user_in_group(request: HttpRequest, group_id: int):
    group: Group = Group.objects.get(id=group_id)
    users: User = group.members.all().order_by("pseudo")
    if request.method == "POST":
        uid: str = request.POST.get("user_id")
        pwd: str = request.POST.get("password", "")
        remember_me: bool = request.POST.get("remember_me") == "on"

        user: User = users.filter(id=uid).first()
        if user and user.check_password(pwd):
            # Connexion successful -> store the id and redirect the user to the dashboard
            request.session["user_id"] = user.id

            if remember_me:
                request.session.set_expiry(SESSION_EXPIRY_DURATION)
            else:
                request.session.set_expiry(0)
            return redirect("dashboard")
        else:
            return render(request, "gifts/choose_user.html", {
                "group": group,
                "users": users,
                "error": "Nom ou mot de passe incorrect"
            })

    return render(request, "gifts/choose_user.html", {
        "group": group,
        "users": users
    })

@require_POST
def add_gift(request: HttpRequest, owner_id: float):
    current: User = get_current_user(request)
    owner: User = get_object_or_404(User, id=owner_id)
    if not current:
        redirect("choose_user")

    title: str = request.POST.get("title", "").strip()
    description: str = request.POST.get("description", "").strip()
    url: str = request.POST.get("url", "").strip()

    if not title:
        return redirect("view_list", user_id=current.id)

    Gift.objects.create(
        owner=owner,
        title=title,
        description=description,
        url=url,
        created_by=current,
    )
    return redirect("view_list", user_id=owner.id)

def logout(request: HttpRequest):
    request.session.flush()
    return redirect("choose_group")

@require_POST
def delete_gift(request: HttpRequest, gift_id: int):
    # the current user, if any
    current: User = get_current_user(request)
    gift: Gift = get_object_or_404(Gift, id=gift_id)

    if not current or gift.created_by != current:
        return HttpResponseForbidden("Non autorisé")

    gift.delete()
    return redirect("view_list", user_id=gift.owner.id)

@require_POST
def edit_gift(request: HttpRequest, gift_id: int):
    current: User = get_current_user(request)
    gift = get_object_or_404(Gift, id=gift_id)

    if not current or gift.owner != current:
        redirect("choose_user")

    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()
    url = request.POST.get("url", "").strip()

    if title:
        gift.title = title
        gift.description = description
        gift.url = url
        gift.save()

    return redirect("view_list", user_id=current.id)

@require_POST
def unreserve_gift(request, gift_id):
    current = get_current_user(request)
    if not current:
        redirect("choose_user")

    try:
        reservation = Reservation.objects.get(gift_id=gift_id, reserver=current)
        reservation.delete()
    except Reservation.DoesNotExist:
        pass  # rien à faire si pas de réservation par cet utilisateur

    # Redirige vers la liste du propriétaire du cadeau
    gift = get_object_or_404(Gift, id=gift_id)
    return redirect("view_list", user_id=gift.owner.id)

@require_POST
def change_password(request: HttpRequest):
    current: User = get_current_user(request)
    if not current:
        redirect("choose_user")

    old_password: str = request.POST.get("old_password")
    new_password: str = request.POST.get("new_password")
    confirm_password: str = request.POST.get("confirm_password")

    if not current.check_password(old_password):
        return render(request, "gifts/change_password.html", {
            "error": "Ancien mot de passe incorrect",
            "current": current
        })

    if new_password != confirm_password:
        return render(request, "gifts/change_password.html", {
            "error": "Les nouveaux mots de passe ne correspondent pas",
            "current": current
        })

    if not new_password:
        return render(request, "gifts/change_password.html", {
            "error": "Le nouveau mot de passe ne peut pas être vide",
            "current": current
        })

    errors: list[str] = []
    if len(new_password) < 8:
        errors.append("Au moins 8 caractères")
    if not re.search(r"[A-Z]", new_password):
        errors.append("Au moins une majuscule")
    if not re.search(r"[a-z]", new_password):
        errors.append("Au moins une minuscule")
    if not re.search(r"[0-9]", new_password):
        errors.append("Au moins un chiffre")

    if errors:
        return render(request, "gifts/change_password.html", {
            "error": "Le mot de passe ne respecte pas les critères : " + ", ".join(errors),
            "current": current
        })

    current.set_password(new_password)
    current.save()
    return redirect("dashboard")  # Redirige vers le dashboard après succès

def change_password_form(request: HttpRequest):
    current: User = get_current_user(request)
    if not current:
        return redirect("choose_user")
    return render(request, "gifts/change_password.html", {"current": current})

