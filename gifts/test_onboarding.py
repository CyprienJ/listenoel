from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext as _

from .models import Group, User
from .onboarding import (
    CURRENT_ONBOARDING_VERSION,
    PENDING_GROUP_INVITE_SESSION_KEY,
    get_onboarding_next_url,
    onboarding_is_complete,
)


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
        self.assertIsNone(user.profile_completed_at)
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

        self.assertRedirects(response, reverse("onboarding_profile"), fetch_redirect_response=False)
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

        self.assertRedirects(response, reverse("onboarding_profile"))
        self.assertEqual(len(mail.outbox), 0)


class OnboardingResolverTest(TestCase):
    def test_anonymous_user_goes_to_welcome(self):
        self.assertEqual(get_onboarding_next_url(AnonymousUser()), reverse("welcome"))

    def test_unverified_user_goes_to_email_verification(self):
        user = User(is_verified=False, onboarding_version=0)

        self.assertEqual(get_onboarding_next_url(user), reverse("verify_email_sent"))

    def test_verified_user_without_profile_goes_to_profile_setup(self):
        user = User(is_verified=True, onboarding_version=0, profile_completed_at=None)

        self.assertFalse(onboarding_is_complete(user))
        self.assertEqual(get_onboarding_next_url(user), reverse("onboarding_profile"))

    def test_user_with_profile_goes_to_group_choice(self):
        user = User(
            is_verified=True,
            onboarding_version=0,
            profile_completed_at=timezone.now(),
        )

        self.assertFalse(onboarding_is_complete(user))
        self.assertEqual(get_onboarding_next_url(user), reverse("onboarding_group"))

    def test_pending_invitation_takes_priority_over_group_choice(self):
        user = User(
            is_verified=True,
            onboarding_version=0,
            profile_completed_at=timezone.now(),
            pending_group_invite_token="ABC123",
        )

        self.assertEqual(
            get_onboarding_next_url(user),
            reverse("join_group", kwargs={"token": "ABC123"}),
        )

    def test_existing_user_at_current_version_is_complete(self):
        user = User(
            is_verified=True,
            onboarding_version=CURRENT_ONBOARDING_VERSION,
            profile_completed_at=timezone.now(),
        )

        self.assertTrue(onboarding_is_complete(user))
        self.assertEqual(get_onboarding_next_url(user), reverse("dashboard"))


class OnboardingProfileTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="profile@example.com",
            username="profile@example.com",
            password="password",
            nickname="",
            is_verified=True,
        )
        self.client.force_login(self.user)

    def test_incomplete_user_is_redirected_from_dashboard_to_profile(self):
        response = self.client.get(reverse("dashboard"))

        self.assertRedirects(response, reverse("onboarding_profile"))

    def test_profile_page_explains_each_piece_of_information(self):
        response = self.client.get(reverse("onboarding_profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, _("This name is visible to people in your groups."))
        self.assertContains(response, _("We do not ask for the year."), html=False)
        self.assertContains(response, _("Optional — it helps members of your groups recognize you."))

    def test_profile_requires_a_nickname(self):
        response = self.client.post(reverse("onboarding_profile"), {"nickname": ""})

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.profile_completed_at)

    def test_profile_rejects_partial_or_impossible_birthday(self):
        partial = self.client.post(
            reverse("onboarding_profile"),
            {"nickname": "Alice", "birthday_month": "2", "birthday_day": ""},
        )
        impossible = self.client.post(
            reverse("onboarding_profile"),
            {"nickname": "Alice", "birthday_month": "2", "birthday_day": "30"},
        )

        self.assertEqual(partial.status_code, 200)
        self.assertEqual(impossible.status_code, 200)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.profile_completed_at)

    def test_profile_can_be_completed_without_birthday_or_photo(self):
        response = self.client.post(reverse("onboarding_profile"), {"nickname": "  Alice  "})

        self.assertRedirects(response, reverse("onboarding_group"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.nickname, "Alice")
        self.assertIsNone(self.user.birthday)
        self.assertFalse(self.user.avatar)
        self.assertIsNotNone(self.user.profile_completed_at)
        self.assertEqual(self.user.onboarding_version, 0)

    def test_profile_saves_birthday_without_year(self):
        response = self.client.post(
            reverse("onboarding_profile"),
            {"nickname": "Alice", "birthday_month": "12", "birthday_day": "24"},
        )

        self.assertRedirects(response, reverse("onboarding_group"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.birthday_month, 12)
        self.assertEqual(self.user.birthday_day, 24)
        self.assertFalse(hasattr(self.user, "birthday_year"))

    def test_completed_profile_cannot_reenter_setup(self):
        self.user.nickname = "Alice"
        self.user.profile_completed_at = timezone.now()
        self.user.save(update_fields=["nickname", "profile_completed_at"])

        response = self.client.get(reverse("onboarding_profile"))

        self.assertRedirects(response, reverse("onboarding_group"))

    def test_photo_editor_returns_to_onboarding_without_completing_profile(self):
        response = self.client.get(reverse("photo_upload_profile"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["back_url"], reverse("onboarding_profile"))
        self.assertTrue(response.context["is_onboarding"])
        self.user.refresh_from_db()
        self.assertIsNone(self.user.profile_completed_at)

    def test_unverified_user_cannot_open_profile_setup(self):
        self.user.is_verified = False
        self.user.save(update_fields=["is_verified"])

        response = self.client.get(reverse("onboarding_profile"))

        self.assertRedirects(response, reverse("verify_email_sent"))


class GroupOnboardingTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="new@example.com",
            username="new@example.com",
            password="password",
            nickname="New member",
            is_verified=True,
            profile_completed_at=timezone.now(),
        )
        self.owner = User.objects.create_user(
            email="owner@example.com",
            username="owner@example.com",
            password="password",
            nickname="SecretOwner",
            is_verified=True,
            profile_completed_at=timezone.now(),
            onboarding_version=CURRENT_ONBOARDING_VERSION,
            onboarding_completed_at=timezone.now(),
        )
        self.group = Group.objects.create(name="Family", created_by=self.owner)
        self.group.members.add(self.owner)
        self.client.force_login(self.user)

    def test_choice_page_offers_create_join_and_later(self):
        response = self.client.get(reverse("onboarding_group"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, _("Create a group"))
        self.assertContains(response, _("Join with a code"))
        self.assertContains(response, _("I'll do this later"))

    def test_skip_is_post_only_and_completes_onboarding(self):
        self.assertEqual(self.client.get(reverse("onboarding_group_skip")).status_code, 405)

        response = self.client.post(reverse("onboarding_group_skip"))

        self.assertRedirects(response, reverse("dashboard"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.onboarding_version, CURRENT_ONBOARDING_VERSION)
        self.assertIsNotNone(self.user.onboarding_completed_at)

    def test_create_group_adds_creator_and_completes_onboarding(self):
        response = self.client.post(reverse("create_group"), {"name": "Friends"})

        created_group = Group.objects.get(name="Friends")
        self.assertRedirects(response, reverse("group_detail", args=[created_group.id]))
        self.assertTrue(created_group.members.filter(pk=self.user.pk).exists())
        self.user.refresh_from_db()
        self.assertTrue(onboarding_is_complete(self.user))

    def test_valid_code_opens_preview_then_post_joins_group(self):
        response = self.client.post(reverse("onboarding_join_group"), {"code": self.group.group_token.lower()})

        preview_url = reverse("join_group", kwargs={"token": self.group.group_token})
        self.assertRedirects(response, preview_url, fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertFalse(onboarding_is_complete(self.user))
        self.assertEqual(self.user.pending_group_invite_token, self.group.group_token)

        preview = self.client.get(preview_url)
        self.assertEqual(preview.status_code, 200)

        confirm_url = reverse("join_group_confirm", kwargs={"token": self.group.group_token})
        self.assertEqual(self.client.get(confirm_url).status_code, 405)
        accepted = self.client.post(confirm_url)

        self.assertRedirects(accepted, reverse("group_detail", args=[self.group.id]))
        self.assertTrue(self.group.members.filter(pk=self.user.pk).exists())
        self.user.refresh_from_db()
        self.assertTrue(onboarding_is_complete(self.user))
        self.assertEqual(self.user.pending_group_invite_token, "")

    def test_accepting_twice_is_idempotent(self):
        confirm_url = reverse("join_group_confirm", kwargs={"token": self.group.group_token})

        self.client.post(confirm_url)
        self.client.post(confirm_url)

        self.assertEqual(self.group.members.filter(pk=self.user.pk).count(), 1)

    def test_acceptance_requires_a_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        response = csrf_client.post(
            reverse("join_group_confirm", kwargs={"token": self.group.group_token})
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.group.members.filter(pk=self.user.pk).exists())

    def test_preview_does_not_complete_an_existing_members_onboarding(self):
        self.group.members.add(self.user)

        response = self.client.get(reverse("join_group", kwargs={"token": self.group.group_token}))

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(onboarding_is_complete(self.user))
        self.assertContains(response, _("Continue to the group"))

    def test_invalid_code_keeps_onboarding_open(self):
        response = self.client.post(reverse("onboarding_join_group"), {"code": "UNKNOWN"}, follow=True)

        self.assertRedirects(response, reverse("onboarding_group"))
        self.assertContains(response, _("No group found with this code."))
        self.user.refresh_from_db()
        self.assertFalse(onboarding_is_complete(self.user))

    def test_invitation_that_becomes_invalid_returns_to_group_choice(self):
        self.user.pending_group_invite_token = "REMOVED"
        self.user.save(update_fields=["pending_group_invite_token"])
        session = self.client.session
        session[PENDING_GROUP_INVITE_SESSION_KEY] = "REMOVED"
        session.save()

        response = self.client.get(reverse("dashboard"), follow=True)

        self.assertRedirects(response, reverse("onboarding_group"))
        self.assertContains(response, _("This invitation is no longer valid. Choose another group."))
        self.user.refresh_from_db()
        self.assertEqual(self.user.pending_group_invite_token, "")


@override_settings(TURNSTILE_ENABLED=False)
class PendingInvitationRegistrationTest(TestCase):
    registration_data = {
        "email": "invited@example.com",
        "password1": "a-secure-test-password-2026",
        "password2": "a-secure-test-password-2026",
    }

    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@example.com",
            username="owner@example.com",
            password="password",
            nickname="PrivateNickname",
            is_verified=True,
            profile_completed_at=timezone.now(),
            onboarding_version=CURRENT_ONBOARDING_VERSION,
        )
        self.group = Group.objects.create(name="Invited group", created_by=self.owner)
        self.group.members.add(self.owner)

    def test_anonymous_preview_is_limited_and_remembers_invitation(self):
        response = self.client.get(reverse("join_group", kwargs={"token": self.group.group_token}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.group.name)
        self.assertContains(response, _("Create an account"))
        self.assertNotContains(response, self.owner.nickname)
        self.assertEqual(
            self.client.session[PENDING_GROUP_INVITE_SESSION_KEY],
            self.group.group_token,
        )

    def test_invitation_survives_registration_verification_and_profile(self):
        invite_url = reverse("join_group", kwargs={"token": self.group.group_token})
        self.client.get(invite_url)
        registration = self.client.post(
            f"{reverse('register')}?next=https://attacker.example/escape",
            self.registration_data,
        )

        self.assertRedirects(registration, reverse("verify_email_sent"))
        user = User.objects.get(email="invited@example.com")
        self.assertEqual(user.pending_group_invite_token, self.group.group_token)

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        verified = self.client.get(reverse("verify_email_confirm", kwargs={"uidb64": uid, "token": token}))
        self.assertRedirects(verified, reverse("onboarding_profile"), fetch_redirect_response=False)

        profile = self.client.post(reverse("onboarding_profile"), {"nickname": "Invited"})
        self.assertRedirects(profile, invite_url, fetch_redirect_response=False)

    def test_persisted_invitation_is_available_on_another_device(self):
        user = User.objects.create_user(
            email="cross-device@example.com",
            username="cross-device@example.com",
            password="password",
            nickname="Cross device",
            is_verified=True,
            profile_completed_at=timezone.now(),
            pending_group_invite_token=self.group.group_token,
        )
        other_client = self.client_class()
        other_client.force_login(user)

        response = other_client.get(reverse("dashboard"))

        self.assertRedirects(
            response,
            reverse("join_group", kwargs={"token": self.group.group_token}),
            fetch_redirect_response=False,
        )
