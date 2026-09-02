from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext as _

from .models import User
from .onboarding import CURRENT_ONBOARDING_VERSION, get_onboarding_next_url, onboarding_is_complete


@override_settings(TURNSTILE_ENABLED=False)
class RegistrationOnboardingTest(TestCase):
    registration_data = {
        "email": "alice@example.com",
        "password1": "a-secure-test-password-2026",
        "password2": "a-secure-test-password-2026",
    }

    def test_registration_only_asks_for_credentials(self):
        response = self.client.get(reverse("register"))

        self.assertEqual(list(response.context["form"].fields), ["email", "password1", "password2"])

    def test_registration_creates_an_incomplete_user_and_opens_verification_page(self):
        response = self.client.post(reverse("register"), self.registration_data)

        self.assertRedirects(response, reverse("verify_email_sent"))
        user = User.objects.get(email="alice@example.com")
        self.assertEqual(user.nickname, "")
        self.assertFalse(user.is_verified)
        self.assertEqual(user.onboarding_version, 0)
        self.assertIsNone(user.onboarding_completed_at)
        self.assertIsNotNone(user.verification_email_sent_at)
        self.assertEqual(len(mail.outbox), 1)

    def test_registration_normalizes_email_and_rejects_case_insensitive_duplicate(self):
        User.objects.create_user(
            email="alice@example.com",
            username="alice@example.com",
            password="password",
            nickname="Alice",
        )
        data = {**self.registration_data, "email": "  ALICE@EXAMPLE.COM "}

        response = self.client.post(reverse("register"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "email", _("A user with that email already exists."))
        self.assertEqual(User.objects.filter(email__iexact="alice@example.com").count(), 1)

    def test_verification_page_displays_recipient_email(self):
        self.client.post(reverse("register"), self.registration_data)

        response = self.client.get(reverse("verify_email_sent"))

        self.assertContains(response, "alice@example.com")

    def test_valid_verification_link_marks_user_verified(self):
        self.client.post(reverse("register"), self.registration_data)
        user = User.objects.get(email="alice@example.com")
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        response = self.client.get(
            reverse("verify_email_confirm", kwargs={"uidb64": uid, "token": token})
        )

        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertTrue(user.is_verified)
        self.assertEqual(user.onboarding_version, 0)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    VERIFICATION_EMAIL_RESEND_COOLDOWN_SECONDS=60,
)
class VerificationEmailCooldownTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="waiting@example.com",
            username="waiting@example.com",
            password="password",
            nickname="",
            is_verified=False,
        )
        self.client.force_login(self.user)

    def test_recent_email_cannot_be_resent(self):
        self.user.verification_email_sent_at = timezone.now()
        self.user.save(update_fields=["verification_email_sent_at"])

        response = self.client.post(reverse("resend_verification"))

        self.assertRedirects(response, reverse("verify_email_sent"))
        self.assertEqual(len(mail.outbox), 0)

    def test_email_can_be_resent_after_cooldown(self):
        previous_sent_at = timezone.now() - timedelta(seconds=61)
        self.user.verification_email_sent_at = previous_sent_at
        self.user.save(update_fields=["verification_email_sent_at"])

        response = self.client.post(reverse("resend_verification"))

        self.assertRedirects(response, reverse("verify_email_sent"))
        self.assertEqual(len(mail.outbox), 1)
        self.user.refresh_from_db()
        self.assertGreater(self.user.verification_email_sent_at, previous_sent_at)

    def test_resend_requires_post(self):
        response = self.client.get(reverse("resend_verification"))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(len(mail.outbox), 0)

    def test_verified_user_does_not_receive_another_email(self):
        self.user.is_verified = True
        self.user.save(update_fields=["is_verified"])

        response = self.client.post(reverse("resend_verification"))

        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(len(mail.outbox), 0)


class OnboardingResolverTest(TestCase):
    def test_anonymous_user_goes_to_welcome(self):
        self.assertEqual(get_onboarding_next_url(AnonymousUser()), reverse("welcome"))

    def test_unverified_user_goes_to_email_verification(self):
        user = User(is_verified=False, onboarding_version=0)

        self.assertEqual(get_onboarding_next_url(user), reverse("verify_email_sent"))

    def test_verified_incomplete_user_temporarily_goes_to_dashboard(self):
        user = User(is_verified=True, onboarding_version=0)

        self.assertFalse(onboarding_is_complete(user))
        self.assertEqual(get_onboarding_next_url(user), reverse("dashboard"))

    def test_user_at_current_version_is_complete(self):
        user = User(is_verified=True, onboarding_version=CURRENT_ONBOARDING_VERSION)

        self.assertTrue(onboarding_is_complete(user))
        self.assertEqual(get_onboarding_next_url(user), reverse("dashboard"))
