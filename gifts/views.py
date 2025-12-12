import random
import re

from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponseForbidden
from django.db import transaction, IntegrityError
from django.views.decorators.http import require_POST

from .models import Person, Gift, Reservation, Family

FOURTEEN_DAYS = 60 * 60 * 24 * 14

def get_current_person(request):
    person_id = request.session.get("person_id")
    if not person_id:
        return None
    return Person.objects.filter(id=person_id).first()

def dashboard(request):
    current = get_current_person(request)
    if not current:
        return redirect("choose_person")

    persons = Person.objects.filter(family=current.family).order_by("name").exclude(id=current.id)

    christmas_emojis = [
        "🎄", "🎁", "🎅", "🤶", "🧑‍🎄", "⛄", "☃️", "❄️", "🌨️", "✨", "🌟", "⭐", "🔔", "🕯️", "🍫", "🦌", "🛷", "🎶", "🎉", "🎊",
    ]
    greeting_emoji = random.choice(christmas_emojis)

    return render(request, "gifts/dashboard.html", {
        "current": current,
        "persons": persons,
        "greeting_emoji": greeting_emoji,
    })


def view_list(request, person_id):
    current = get_current_person(request)
    person = get_object_or_404(Person, id=person_id)

    gifts = Gift.objects.filter(owner=person).order_by("created_at")

    gifts_with_info = []

    if current and current.id == person.id:
        # Propriétaire : on ne montre pas les réservations
        for g in gifts:
            gifts_with_info.append({
                "gift": g,
                "is_reserved": None,
                "reserved_by": None
            })
    else:
        reservations = {r.gift_id: r for r in Reservation.objects.filter(gift__in=gifts)}
        for g in gifts:
            r = reservations.get(g.id)
            gifts_with_info.append({
                "gift": g,
                "is_reserved": bool(r),
                "reserved_by": r.reserver if r else None
            })

    return render(request, "gifts/view_list.html", {
        "person": person,
        "gifts_with_info": gifts_with_info,
        "current": current
    })


@transaction.atomic
def reserve_gift(request, gift_id):
    current = get_current_person(request)
    if not current:
        return HttpResponseForbidden("Non autorisé")

    gift = get_object_or_404(Gift, id=gift_id)

    if gift.owner_id == current.id:
        return HttpResponseForbidden("Impossible sur votre propre liste")

    try:
        Reservation.objects.create(gift=gift, reserver=current)
    except IntegrityError:
        return JsonResponse({"success": False, "error": "Déjà réservé"}, status=409)

    return JsonResponse({"success": True})

def choose_family(request):
    current = get_current_person(request)
    if current:
        return redirect("dashboard")
    families = Family.objects.all().order_by("name")
    return render(request, "gifts/choose_family.html", {"families": families})


def choose_person_in_family(request, family_id):
    family = Family.objects.get(id=family_id)
    persons = family.members.all().order_by("name")

    if request.method == "POST":
        pid = request.POST.get("person_id")
        pwd = request.POST.get("password", "")
        remember_me = request.POST.get("remember_me") == "on"

        person = persons.filter(id=pid).first()
        if person and person.check_password(pwd):
            # Connexion réussie → stocker l'id et rediriger vers dashboard
            request.session["person_id"] = person.id

            if remember_me:
                request.session.set_expiry(FOURTEEN_DAYS)
            else:
                request.session.set_expiry(0)

            return redirect("dashboard")
        else:
            return render(request, "gifts/choose_person.html", {
                "family": family,
                "persons": persons,
                "error": "Nom ou mot de passe incorrect"
            })

    return render(request, "gifts/choose_person.html", {
        "family": family,
        "persons": persons
    })


@require_POST
def add_gift(request):
    current = get_current_person(request)
    if not current:
        return HttpResponseForbidden("Non autorisé")

    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()
    url = request.POST.get("url", "").strip()

    if not title:
        return redirect("view_list", person_id=current.id)

    Gift.objects.create(
        owner=current,
        title=title,
        description=description,
        url=url
    )
    return redirect("view_list", person_id=current.id)

def logout(request):
    request.session.flush()
    return redirect("choose_family")

@require_POST
def delete_gift(request, gift_id):
    current = get_current_person(request)
    gift = get_object_or_404(Gift, id=gift_id)

    if not current or gift.owner != current:
        return HttpResponseForbidden("Non autorisé")

    gift.delete()
    return redirect("view_list", person_id=current.id)

@require_POST
def edit_gift(request, gift_id):
    current = get_current_person(request)
    gift = get_object_or_404(Gift, id=gift_id)

    if not current or gift.owner != current:
        return HttpResponseForbidden("Non autorisé")

    title = request.POST.get("title", "").strip()
    description = request.POST.get("description", "").strip()
    url = request.POST.get("url", "").strip()

    if title:
        gift.title = title
        gift.description = description
        gift.url = url
        gift.save()

    return redirect("view_list", person_id=current.id)

@require_POST
def unreserve_gift(request, gift_id):
    current = get_current_person(request)
    if not current:
        return HttpResponseForbidden("Non autorisé")

    try:
        reservation = Reservation.objects.get(gift_id=gift_id, reserver=current)
        reservation.delete()
    except Reservation.DoesNotExist:
        pass  # rien à faire si pas de réservation par cet utilisateur

    # Redirige vers la liste du propriétaire du cadeau
    gift = get_object_or_404(Gift, id=gift_id)
    return redirect("view_list", person_id=gift.owner.id)

@require_POST
def change_password(request):
    current = get_current_person(request)
    if not current:
        return HttpResponseForbidden("Non autorisé")

    old_password = request.POST.get("old_password")
    new_password = request.POST.get("new_password")
    confirm_password = request.POST.get("confirm_password")

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

    errors = []
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

def change_password_form(request):
    current = get_current_person(request)
    if not current:
        return redirect("choose_person")
    return render(request, "gifts/change_password.html", {"current": current})

