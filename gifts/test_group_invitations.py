from unittest.mock import patch

from django.core import mail
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Group, GroupInvitationDispatch, User
from .onboarding import (
    CURRENT_ONBOARDING_VERSION,
    PENDING_GROUP_INVITE_SESSION_KEY,
    group_invitation_pending_value,
)


class GroupInvitationMigrationTest(TransactionTestCase):
    migrate_from = [("gifts", "0041_user_pending_group_invite_token")]
    migrate_to = [("gifts", "0042_group_invitation_token_and_dispatch")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        old_user = old_apps.get_model("gifts", "User").objects.create(
            email="migration@example.com",
            username="migration@example.com",
            nickname="Migration",
        )
        old_apps.get_model("gifts", "Group").objects.create(
            name="Existing group",
            group_token="OLDCODE1",
            created_by=old_user,
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate(self.migrate_to)
        super().tearDown()

    def test_existing_short_code_is_preserved_and_secure_token_is_created(self):
        group = self.apps.get_model("gifts", "Group").objects.get(name="Existing group")

        self.assertEqual(group.group_token, "OLDCODE1")
        self.assertGreaterEqual(len(group.invitation_token), 40)


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    PUBLIC_BASE_URL="https://gifts.example",
    TURNSTILE_ENABLED=False,
)
class GroupInvitationTest(TestCase):
    registration_data = {
        "email": "invited@example.com",
        "password1": "a-secure-test-password-2026",
        "password2": "a-secure-test-password-2026",
    }

    def setUp(self):
        completed_at = timezone.now()
        self.owner = User.objects.create_user(
            email="owner@example.com",
            username="owner@example.com",
            password="password",
            nickname="PrivateOwner",
            is_verified=True,
            profile_completed_at=completed_at,
            onboarding_version=CURRENT_ONBOARDING_VERSION,
            onboarding_completed_at=completed_at,
        )
        self.member = User.objects.create_user(
            email="member@example.com",
            username="member@example.com",
            password="password",
            nickname="Member",
            is_verified=True,
            profile_completed_at=completed_at,
            onboarding_version=CURRENT_ONBOARDING_VERSION,
            onboarding_completed_at=completed_at,
        )
        self.outsider = User.objects.create_user(
            email="outsider@example.com",
            username="outsider@example.com",
            password="password",
            nickname="Outsider",
            is_verified=True,
            profile_completed_at=completed_at,
            onboarding_version=CURRENT_ONBOARDING_VERSION,
            onboarding_completed_at=completed_at,
        )
        self.group = Group.objects.create(name="Family", created_by=self.owner)
        self.group.members.add(self.owner, self.member)

    def invitation_url(self, token=None):
        return reverse("group_invitation", kwargs={"token": token or self.group.invitation_token})

    def test_group_has_distinct_short_code_and_secure_link_token(self):
        self.assertNotEqual(self.group.group_token, self.group.invitation_token)
        self.assertLessEqual(len(self.group.group_token), 12)
        self.assertGreaterEqual(len(self.group.invitation_token), 40)

    def test_invitation_screen_uses_configured_domain_and_current_language(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("group_invitations", args=[self.group.id]))

        self.assertEqual(response.status_code, 200)
        expected_url = f"https://gifts.example{self.invitation_url()}"
        self.assertEqual(response.context["invitation_url"], expected_url)
        self.assertContains(response, expected_url)
        self.assertContains(response, self.group.group_token)

    def test_invitation_screen_is_available_to_members_but_not_outsiders(self):
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(reverse("group_invitations", args=[self.group.id])).status_code, 200)

        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("group_invitations", args=[self.group.id])).status_code, 403)

    def test_anonymous_secure_preview_is_limited_and_remembered(self):
        response = self.client.get(self.invitation_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.group.name)
        self.assertNotContains(response, self.owner.nickname)
        self.assertEqual(
            self.client.session[PENDING_GROUP_INVITE_SESSION_KEY],
            group_invitation_pending_value(self.group.invitation_token),
        )

    def test_secure_invitation_acceptance_is_post_only_csrf_protected_and_idempotent(self):
        self.client.force_login(self.outsider)
        accept_url = reverse("group_invitation_accept", kwargs={"token": self.group.invitation_token})

        self.assertEqual(self.client.get(accept_url).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.outsider)
        self.assertEqual(csrf_client.post(accept_url).status_code, 403)

        self.client.post(accept_url)
        self.client.post(accept_url)

        self.assertEqual(self.group.members.filter(pk=self.outsider.pk).count(), 1)

    def test_regenerating_link_invalidates_old_link_without_changing_short_code(self):
        self.client.force_login(self.owner)
        old_link_token = self.group.invitation_token
        old_code = self.group.group_token

        response = self.client.post(reverse("regenerate_group_invitation_token", args=[self.group.id]))

        self.assertRedirects(response, reverse("group_invitations", args=[self.group.id]))
        self.group.refresh_from_db()
        self.assertNotEqual(self.group.invitation_token, old_link_token)
        self.assertEqual(self.group.group_token, old_code)
        old_link = self.client.get(self.invitation_url(old_link_token))
        self.assertEqual(old_link.status_code, 404)
        self.assertNotContains(old_link, self.group.name, status_code=404)
        self.assertEqual(self.client.get(self.invitation_url()).status_code, 302)

    def test_email_addresses_are_deduplicated_and_messages_are_separate(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("send_group_invitation_emails", args=[self.group.id]),
            {"emails": "Alice@example.com, alice@example.com\nbob@example.com"},
        )

        self.assertRedirects(response, reverse("group_invitations", args=[self.group.id]))
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, ["alice@example.com"])
        self.assertEqual(mail.outbox[1].to, ["bob@example.com"])
        for message in mail.outbox:
            self.assertIn(f"https://gifts.example{self.invitation_url()}", message.body)
            self.assertIn("vous invite à rejoindre", message.body)
            self.assertNotIn("bob@example.com", message.body)
            self.assertNotIn("alice@example.com", message.body)

        dispatch = GroupInvitationDispatch.objects.get()
        self.assertEqual(dispatch.requested_count, 2)
        self.assertEqual(dispatch.sent_count, 2)
        self.assertFalse(any(field.name == "email" for field in dispatch._meta.fields))

    def test_invalid_email_does_not_send_any_message(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("send_group_invitation_emails", args=[self.group.id]),
            {"emails": "valid@example.com, not-an-email"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(GroupInvitationDispatch.objects.exists())

    @override_settings(
        GROUP_INVITATION_MAX_RECIPIENTS_PER_USER_WINDOW=2,
        GROUP_INVITATION_MAX_RECIPIENTS_PER_GROUP_WINDOW=10,
    )
    def test_sender_rate_limit_applies_across_groups(self):
        other_group = Group.objects.create(name="Friends", created_by=self.owner)
        other_group.members.add(self.owner)
        self.client.force_login(self.owner)
        self.client.post(
            reverse("send_group_invitation_emails", args=[self.group.id]),
            {"emails": "one@example.com two@example.com"},
        )

        limited = self.client.post(
            reverse("send_group_invitation_emails", args=[other_group.id]),
            {"emails": "three@example.com"},
        )

        self.assertEqual(limited.status_code, 429)
        self.assertEqual(len(mail.outbox), 2)

    @override_settings(
        GROUP_INVITATION_MAX_RECIPIENTS_PER_USER_WINDOW=10,
        GROUP_INVITATION_MAX_RECIPIENTS_PER_GROUP_WINDOW=1,
    )
    def test_group_rate_limit_applies_across_senders(self):
        self.client.force_login(self.owner)
        self.client.post(
            reverse("send_group_invitation_emails", args=[self.group.id]),
            {"emails": "one@example.com"},
        )
        self.client.force_login(self.member)

        limited = self.client.post(
            reverse("send_group_invitation_emails", args=[self.group.id]),
            {"emails": "two@example.com"},
        )

        self.assertEqual(limited.status_code, 429)
        self.assertEqual(len(mail.outbox), 1)

    @patch("gifts.group_invitations.send_mail", side_effect=[1, RuntimeError("provider unavailable")])
    def test_partial_provider_failure_keeps_group_and_allows_retry(self, mocked_send_mail):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("send_group_invitation_emails", args=[self.group.id]),
            {"emails": "one@example.com two@example.com"},
            follow=True,
        )

        self.assertRedirects(response, reverse("group_invitations", args=[self.group.id]))
        self.assertContains(response, "Certaines invitations n’ont pas pu être envoyées")
        self.assertTrue(Group.objects.filter(pk=self.group.pk).exists())
        dispatch = GroupInvitationDispatch.objects.get()
        self.assertEqual((dispatch.sent_count, dispatch.failed_count), (1, 1))
        self.assertEqual(mocked_send_mail.call_count, 2)

    def test_secure_invitation_survives_registration_and_profile(self):
        invitation_url = self.invitation_url()
        self.client.get(invitation_url)
        self.client.post(reverse("register"), self.registration_data)
        user = User.objects.get(email=self.registration_data["email"])
        user.is_verified = True
        user.save(update_fields=["is_verified"])

        response = self.client.post(reverse("onboarding_profile"), {"nickname": "Invited"})

        self.assertRedirects(response, invitation_url, fetch_redirect_response=False)
        user.refresh_from_db()
        self.assertEqual(
            user.pending_group_invite_token,
            group_invitation_pending_value(self.group.invitation_token),
        )
