from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordChangeView
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.core.management import call_command
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from gifts.demo import DEMO_EMAIL, is_demo_user
from gifts.forms import LocalUserCreationForm, UserProfileForm
from gifts.models import User
from gifts.photo_presets import is_valid_photo_preset, list_photo_presets
from gifts.turnstile import verify_turnstile


def send_verification_email(request, user):
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    domain = get_current_site(request).domain

    link = f"https://{domain}{reverse('verify_email_confirm', kwargs={'uidb64': uid, 'token': token})}"

    context = {"nickname": user.nickname, "verification_link": link}
    subject = _("Verify your email address on Nos Cadeaux!")
    message_txt = render_to_string("emails/verify_email.txt", context)
    message_html = render_to_string("emails/verify_email.html", context)

    send_mail(subject, message_txt, None, [user.email], html_message=message_html)


def delete_avatar_file(storage, name):
    if name:
        storage.delete(name)


def save_profile_form(request, form, old_email, old_avatar_storage, old_avatar_name):
    user = form.save(commit=False)

    if "avatar" in request.FILES:
        delete_avatar_file(old_avatar_storage, old_avatar_name)
        user.avatar_preset = ""

    if user.email != old_email:
        user.is_verified = False
        user.save()
        send_verification_email(request, user)
        messages.success(request, _("Profile updated! Please verify your new email address."))
        return redirect("verify_email_sent")

    user.save()
    messages.success(request, _("Your profile has been updated!"))
    return redirect("account")


@login_required
@require_http_methods(["GET", "POST"])
def account(request):
    if is_demo_user(request.user) and request.method == "POST":
        return HttpResponseForbidden(_("The public demo account profile cannot be changed."))

    if request.method == "POST":
        old_email = request.user.email
        old_avatar = request.user.avatar
        old_avatar_name = old_avatar.name if old_avatar else ""
        old_avatar_storage = old_avatar.storage
        form = UserProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            return save_profile_form(request, form, old_email, old_avatar_storage, old_avatar_name)
    else:
        form = UserProfileForm(instance=request.user)

    return render(request, "account/account.html", {"form": form})


@login_required
@require_POST
def delete_account(request):
    if is_demo_user(request.user):
        return HttpResponseForbidden(_("The public demo account cannot be deleted."))

    user = request.user
    logout(request)
    user.delete()
    messages.success(request, _("Your account has been successfully deleted."))
    return redirect("welcome")


@require_GET
def verify_email_sent(request):
    if not request.user.is_authenticated:
        return redirect("welcome")
    if request.user.is_verified:
        return redirect("dashboard")
    return render(request, "gifts/verify_email_sent.html")


@require_GET
def verify_email_confirm(request, uidb64, token):
    call_command("cleanup_unverified_users")

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_verified = True
        user.save()
        messages.success(request, _("Your account is now verified !"))
        return redirect("dashboard")
    else:
        messages.error(request, _("The verification link is invalid"))
        return redirect("welcome")


@login_required
@require_http_methods(["GET", "POST"])
def resend_verification(request):
    if not request.user.is_authenticated:
        return redirect("welcome")
    if request.user.is_verified:
        messages.success(request, _("Your email is already verified."))
        return redirect("dashboard")
    send_verification_email(request, request.user)
    messages.success(request, _("A new verification email has been sent."))
    return redirect("verify_email_sent")


def set_profile_preset(user, preset):
    if not is_valid_photo_preset("profile", preset):
        return JsonResponse({"success": False, "error": _("Invalid preset photo.")}, status=400)

    delete_avatar_file(user.avatar.storage, user.avatar.name)
    user.avatar = None
    user.avatar_preset = preset
    user.save(update_fields=["avatar", "avatar_preset"])
    return JsonResponse({"success": True, "url": user.display_avatar_url})


def set_profile_photo(user, uploaded):
    if not uploaded:
        return JsonResponse({"success": False, "error": "No file"}, status=400)

    delete_avatar_file(user.avatar.storage, user.avatar.name)
    user.avatar = uploaded
    user.avatar_preset = ""
    user.save(update_fields=["avatar", "avatar_preset"])
    return JsonResponse({"success": True})


@login_required
@require_http_methods(["GET", "POST"])
def photo_upload(request):
    if is_demo_user(request.user) and request.method == "POST":
        return JsonResponse(
            {"success": False, "error": _("The public demo profile picture cannot be changed.")},
            status=403,
        )

    if request.method == "POST":
        preset = request.POST.get("preset", "")
        if preset:
            return set_profile_preset(request.user, preset)

        uploaded = request.FILES.get("photo")
        return set_profile_photo(request.user, uploaded)
    return render(
        request,
        "photos/photo_upload.html",
        {
            "context_type": "profile",
            "photo_presets": list_photo_presets("profile"),
            "back_url": reverse("account"),
        },
    )


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    call_command("cleanup_unverified_users")

    if request.method == "POST":
        form = LocalUserCreationForm(request.POST)
        if form.is_valid():
            if settings.TURNSTILE_ENABLED and not verify_turnstile(request, action="register"):
                form.add_error(None, _("Human verification failed. Please try again."))
                return render(
                    request,
                    "registration/register.html",
                    {"form": form, "turnstile_site_key": settings.TURNSTILE_SITE_KEY},
                )
            user = form.save()
            user.last_seen_version = settings.APP_VERSION
            user.save(update_fields=["last_seen_version"])

            login(request, user, backend="gifts.backends.CaseInsensitiveModelBackend")
            send_verification_email(request, user)

            return redirect("dashboard")
    else:
        form = LocalUserCreationForm()
    return render(
        request,
        "registration/register.html",
        {
            "form": form,
            "turnstile_site_key": settings.TURNSTILE_SITE_KEY if settings.TURNSTILE_ENABLED else "",
        },
    )


@require_GET
def demo_login(request):
    call_command("reset_demo", lazy=True)
    user = User.objects.get(email=DEMO_EMAIL, is_demo=True)
    login(request, user, backend="gifts.backends.CaseInsensitiveModelBackend")
    messages.info(request, _("You are using a public demo account. Demo data resets every 15 minutes."))
    return redirect("dashboard")


class DemoProtectedPasswordChangeView(PasswordChangeView):
    def dispatch(self, request, *args, **kwargs):
        if is_demo_user(request.user):
            return HttpResponseForbidden(_("The public demo account password cannot be changed."))
        return super().dispatch(request, *args, **kwargs)
