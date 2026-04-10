import os

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.core.mail import send_mail
from django.core.management import call_command
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from gifts.forms import LocalUserCreationForm, UserProfileForm
from gifts.models import User


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


@login_required
@require_http_methods(["GET", "POST"])
def account(request):
    if request.method == "POST":
        old_email = request.user.email
        old_avatar = request.user.avatar
        form = UserProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            user = form.save(commit=False)

            if "avatar" in request.FILES and old_avatar and os.path.isfile(old_avatar.path):
                os.remove(old_avatar.path)

            if user.email != old_email:
                user.is_verified = False
                user.save()
                send_verification_email(request, user)
                messages.success(request, _("Profile updated! Please verify your new email address."))
                return redirect("verify_email_sent")

            user.save()
            messages.success(request, _("Your profile has been updated!"))
            return redirect("account")
    else:
        form = UserProfileForm(instance=request.user)

    return render(request, "account/account.html", {"form": form})


@login_required
@require_POST
def delete_account(request):
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


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    call_command("cleanup_unverified_users")

    if request.method == "POST":
        form = LocalUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()

            login(request, user, backend="gifts.backends.CaseInsensitiveModelBackend")
            send_verification_email(request, user)

            return redirect("dashboard")
    else:
        form = LocalUserCreationForm()
    return render(request, "registration/register.html", {"form": form})
