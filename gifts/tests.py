import io
import os
import shutil
import tempfile
from datetime import timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from PIL import Image

from .models import Gift, Group, User


def make_image(name="test.jpg", width=200, height=200):
    img = Image.new("RGB", (width, height), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/jpeg")


def create_users():
    user1 = User.objects.create_user(
        username="user1@test.com", email="user1@test.com", password="password", is_verified=True, nickname="User1"
    )
    user2 = User.objects.create_user(
        username="user2@test.com", email="user2@test.com", password="password", is_verified=True, nickname="User2"
    )
    user3 = User.objects.create_user(
        username="user3@test.com", email="user3@test.com", password="password", is_verified=True, nickname="User3"
    )
    return user1, user2, user3


class UserCleanupTest(TestCase):
    def setUp(self):
        self.user1, self.user2, self.user3 = create_users()

    def test_cleanup_unverified_users_command(self):
        # Create a verified user

        # set user2 and 3 as not verified
        self.user2.is_verified = False
        self.user2.save()

        self.user3.is_verified = False
        self.user3.save()

        # Manually set date_joined to 31 minutes ago
        self.user3.date_joined = timezone.now() - timedelta(minutes=31)
        self.user3.save()

        # Run command
        call_command("cleanup_unverified_users")

        # Check results
        self.assertTrue(User.objects.filter(email="user1@test.com").exists())
        self.assertTrue(User.objects.filter(email="user2@test.com").exists())
        self.assertFalse(User.objects.filter(email="user3@test.com").exists())

    def test_cleanup_in_view(self):
        # Create an unverified user (old)
        self.user1.is_verified = False
        self.user1.date_joined = timezone.now() - timedelta(minutes=31)
        self.user1.save()

        # Using reverse to be sure about the URL
        self.client.get(reverse("register"))

        self.assertFalse(User.objects.filter(email="user1@test.com").exists())


class AccessControlTest(TestCase):
    def setUp(self):

        user1, user2, _ = create_users()
        user1.is_verified = False
        user1.save()

        self.unverified_user = user1

        self.verified_user = user2

    def test_anonymous_access(self):
        """
        Test access for an unauthenticated user.
        - login/register : OK (200)
        - welcome : OK (200)
        - dashboard/account/etc : Redirect to login (302)
        """
        # OK
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)
        self.assertEqual(self.client.get(reverse("register")).status_code, 200)
        self.assertEqual(self.client.get(reverse("welcome")).status_code, 200)

        # Redirect to login by @login_required
        protected_urls = [
            reverse("dashboard"),
            reverse("account"),
            reverse("create_group"),
        ]
        for url in protected_urls:
            response = self.client.get(url)
            self.assertRedirects(response, reverse("login") + f"?next={url}")

    def test_unverified_user_access(self):
        """
        Test access for a logged-in but unverified user.
        - login : OK (200)
        - register : Redirect to verify_email_sent (302)
        - welcome : Redirect to verify_email_sent (302)
        - verify_email_sent/resend/account/logout : OK (200 or 302 depending on action)
        - dashboard/groups/etc : Redirect to verify_email_sent (302) via middleware
        """
        self.client.force_login(self.unverified_user)

        # Django's LoginView does not automatically redirect if accessed via GET while already logged in
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)

        # register is redirected by middleware (as it is not in allowed_urls)
        self.assertRedirects(self.client.get(reverse("register")), reverse("verify_email_sent"))

        # welcome redirects directly to verify_email_sent for unverified users
        self.assertRedirects(self.client.get(reverse("welcome")), reverse("verify_email_sent"))

        # Authorized access for unverified users
        self.assertEqual(self.client.get(reverse("verify_email_sent")).status_code, 200)
        self.assertEqual(self.client.get(reverse("account")).status_code, 200)

        # URLs blocked by middleware and redirected to verify_email_sent
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("verify_email_sent"))

    def test_verified_user_access(self):
        """
        Test access for a logged-in and verified user.
        - login/register/welcome : Redirect to dashboard (302)
        - verify_email_sent/resend : Redirect to dashboard (302) (since already verified)
        - dashboard/profile/groups/etc : OK (200)
        """
        self.client.force_login(self.verified_user)

        # Redirect to dashboard
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)
        self.assertRedirects(self.client.get(reverse("register")), reverse("dashboard"))
        self.assertRedirects(self.client.get(reverse("welcome")), reverse("dashboard"))

        # Redirect to dashboard as already verified
        self.assertRedirects(self.client.get(reverse("verify_email_sent")), reverse("dashboard"))
        self.assertRedirects(self.client.get(reverse("resend_verification")), reverse("dashboard"))

        # Authorized access
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("account")).status_code, 200)

        # For @require_POST views, we just test that we are not redirected by the middleware
        # (thus 405 instead of 302 to verify_email_sent)
        self.assertEqual(self.client.get(reverse("create_group")).status_code, 405)


class PasswordResetTest(TestCase):
    def setUp(self):

        user1, _, _ = create_users()

        self.user = user1

    def test_password_reset_flow(self):
        # 1. Reset request
        response = self.client.post(reverse("account/password_reset"), {"email": "user1@test.com"})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("account/password_reset_done"))

        # Verify that an email was sent
        self.assertEqual(len(mail.outbox), 1)
        reset_mail = mail.outbox[0]
        self.assertIn("user1@test.com", reset_mail.to)

        # Verify that the email contains HTML (since we configured html_email_template_name)
        self.assertTrue(any(alt[1] == "text/html" for alt in reset_mail.alternatives))

        # 2. Verify access to password_reset_done
        response = self.client.get(reverse("account/password_reset_done"))
        self.assertEqual(response.status_code, 200)

    def test_password_reset_unverified_user(self):
        self.user.is_verified = False
        self.user.save()

        self.client.force_login(self.user)
        # Should not be redirected to verify_email_sent by the middleware
        response = self.client.get(reverse("account/password_reset"))
        self.assertEqual(response.status_code, 200)

    def test_password_reset_confirm_unverified_user(self):
        self.user.is_verified = False
        self.user.save()

        url = reverse("account/password_reset_confirm", kwargs={"uidb64": "MQ", "token": "abc-123"})

        self.client.force_login(self.user)
        # Should not be redirected to verify_email_sent by the middleware
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class GiftAccessControlTest(TestCase):
    def setUp(self):

        self.user1, self.user2, self.user3 = create_users()

        # Group between User1 and User2
        self.group = Group.objects.create(name="Group 1-2")
        self.group.members.add(self.user1, self.user2)

        # Gift from User1 (created by himself)
        self.gift_user1 = Gift.objects.create(owner=self.user1, created_by=self.user1, title="Gift User1")

        # Surprise for User1 created by User2
        self.surprise_user1 = Gift.objects.create(owner=self.user1, created_by=self.user2, title="Surprise User1")

    def test_view_list_access(self):
        """A user can only access lists of himself or people with whom he shares at least one group"""
        self.client.force_login(self.user2)
        # User2 shares a group with User1
        self.assertEqual(self.client.get(reverse("view_list", args=[self.user1.id])).status_code, 200)

        self.client.force_login(self.user3)
        # User3 does not share a group with User1
        self.assertEqual(self.client.get(reverse("view_list", args=[self.user1.id])).status_code, 403)

    def test_edit_gift_access(self):
        """A user can only edit his gifts or surprises from groups he is in"""
        # User1 edits his own gift
        self.client.force_login(self.user1)
        response = self.client.post(reverse("edit_gift", args=[self.gift_user1.id]), {"title": "Updated Title"})
        self.assertEqual(response.status_code, 302)
        self.gift_user1.refresh_from_db()
        self.assertEqual(self.gift_user1.title, "Updated Title")

        # User2 edits the surprise he created for User1
        self.client.force_login(self.user2)
        response = self.client.post(reverse("edit_gift", args=[self.surprise_user1.id]), {"title": "Updated Surprise"})
        self.assertEqual(response.status_code, 302)
        self.surprise_user1.refresh_from_db()
        self.assertEqual(self.surprise_user1.title, "Updated Surprise")

        # User3 attempts to edit User1's gift (should fail)
        self.client.force_login(self.user3)
        response = self.client.post(reverse("edit_gift", args=[self.gift_user1.id]), {"title": "Hacked Title"})
        # Currently this probably passes (200 or 302), we expect 403 or 404
        self.assertIn(response.status_code, [403, 404])

    def test_delete_gift_access(self):
        """A user can only delete his gifts or surprises from groups he is in"""
        # User3 attempts to delete User1's gift
        self.client.force_login(self.user3)
        response = self.client.post(reverse("delete_gift", args=[self.gift_user1.id]))
        self.assertIn(response.status_code, [403, 404])
        self.assertTrue(Gift.objects.filter(id=self.gift_user1.id).exists())


class SubscriptionTest(TestCase):
    def setUp(self):

        self.user1, self.user2, self.user3 = create_users()
        self.group = Group.objects.create(name="Group 1-2")
        self.group.members.add(self.user1, self.user2)

    def test_toggle_subscription(self):
        self.client.force_login(self.user2)
        # Subscribe
        response = self.client.post(reverse("toggle_subscription", args=[self.user1.id]))
        self.assertRedirects(response, reverse("view_list", args=[self.user1.id]))
        self.assertTrue(self.user2.subscriptions.filter(id=self.user1.id).exists())

        # Unsubscribe
        response = self.client.post(reverse("toggle_subscription", args=[self.user1.id]))
        self.assertRedirects(response, reverse("view_list", args=[self.user1.id]))
        self.assertFalse(self.user2.subscriptions.filter(id=self.user1.id).exists())

    def test_subscribe_self(self):
        self.client.force_login(self.user1)
        response = self.client.post(reverse("toggle_subscription", args=[self.user1.id]))
        self.assertEqual(response.status_code, 403)

    def test_subscribe_no_common_group(self):
        self.client.force_login(self.user3)
        response = self.client.post(reverse("toggle_subscription", args=[self.user1.id]))
        self.assertEqual(response.status_code, 403)

    def test_notification_sent_on_add_gift(self):
        # User2 subscribes to User1
        self.user2.subscriptions.add(self.user1)

        self.client.force_login(self.user1)
        # User1 adds a gift to his own list
        response = self.client.post(
            reverse("add_gift", args=[self.user1.id]),
            {"title": "New Gift", "description": "A cool gift", "url": "https://example.com"},
        )
        self.assertRedirects(response, reverse("view_list", args=[self.user1.id]))

        # Verify email delivery
        self.assertEqual(len(mail.outbox), 1)
        notification_mail = mail.outbox[0]
        self.assertIn(self.user2.email, notification_mail.to)
        # The subject is translated to French by default in tests because LANGUAGE_CODE='fr'
        self.assertIn("User1", notification_mail.subject)
        self.assertIn("New Gift", notification_mail.body)
        self.assertIn("A cool gift", notification_mail.body)
        self.assertIn("https://example.com", notification_mail.body)

        # Verify unsubscribe link
        self.assertIn("/unsubscribe/", notification_mail.body)

    def test_unsubscribe_token(self):
        self.user2.subscriptions.add(self.user1)

        uid = urlsafe_base64_encode(force_bytes(self.user1.pk))
        token = "dummy-token"
        url = reverse("unsubscribe_token", args=[uid, token])

        self.client.force_login(self.user2)
        # Test with GET because button changed to link
        response = self.client.get(url)
        self.assertRedirects(response, reverse("view_list", args=[self.user1.id]))
        self.assertFalse(self.user2.subscriptions.filter(id=self.user1.id).exists())

    def test_no_notification_if_not_owner_adding(self):
        # User2 subscribes to User1
        self.user2.subscriptions.add(self.user1)

        self.client.force_login(self.user2)
        # User2 add a surprise to User1's list
        self.client.post(reverse("add_gift", args=[self.user1.id]), {"title": "Surprise"})

        # No mail sent because it is a surprise
        self.assertEqual(len(mail.outbox), 0)

    def test_notification_visibility_restriction(self):
        # User2 subscribes to User1
        self.user2.subscriptions.add(self.user1)

        # User1 create another group with User3
        group2 = Group.objects.create(name="Group 1-3")
        group2.members.add(self.user1, self.user3)

        self.client.force_login(self.user1)

        # User1 add a gift visible only to 1-3 group
        self.client.post(reverse("add_gift", args=[self.user1.id]), {"title": "Secret Gift", "visible_in": [group2.id]})

        # User2 shouldn't receive a notification
        self.assertEqual(len(mail.outbox), 0)

        # User3 subscribes to User1
        self.user3.subscriptions.add(self.user1)
        mail.outbox = []

        # User1 add a gift visible to everybody
        self.client.post(reverse("add_gift", args=[self.user1.id]), {"title": "Public Gift"})

        # User2 and User3 receive a mail
        self.assertEqual(len(mail.outbox), 2)

    def test_add_gift_access(self):
        """Add a gift/surprise only if there is a common group"""
        self.client.force_login(self.user3)
        # User3 attempts to add a gift to User1
        response = self.client.post(reverse("add_gift", args=[self.user1.id]), {"title": "Bad Surprise"})
        self.assertIn(response.status_code, [403, 404])
        self.assertFalse(Gift.objects.filter(title="Bad Surprise").exists())


class GroupManagementTest(TestCase):
    def setUp(self):

        self.creator, self.member, self.outsider = create_users()

        self.group = Group.objects.create(name="Original Name", created_by=self.creator)
        self.group.members.add(self.creator, self.member)
        self.original_token = self.group.group_token

    def test_edit_group_name_as_creator(self):
        self.client.force_login(self.creator)
        response = self.client.post(
            reverse("edit_group", args=[self.group.id]), {"name": "New Name", "description": ""}
        )
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, "New Name")

    def test_edit_group_name_as_member(self):
        self.client.force_login(self.member)
        response = self.client.post(
            reverse("edit_group", args=[self.group.id]), {"name": "New Name", "description": ""}
        )
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, "New Name")

    def test_regenerate_token_as_creator(self):
        self.client.force_login(self.creator)
        response = self.client.post(reverse("regenerate_group_token", args=[self.group.id]))
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertNotEqual(self.group.group_token, self.original_token)
        self.assertTrue(len(self.group.group_token) > 0)

    def test_regenerate_token_as_member(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse("regenerate_group_token", args=[self.group.id]))
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertNotEqual(self.group.group_token, self.original_token)
        self.assertTrue(len(self.group.group_token) > 0)


class GroupImageTest(TestCase):
    def setUp(self):
        self.user, self.member, self.outsider = create_users()
        self.group = Group.objects.create(name="Photo Group", created_by=self.user)
        self.group.members.add(self.user, self.member)
        self.media_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.media_dir, ignore_errors=True)

    def test_upload_image_as_member(self):
        """A member can upload a group image."""
        self.client.force_login(self.member)
        with override_settings(MEDIA_ROOT=self.media_dir):
            response = self.client.post(
                reverse("edit_group", args=[self.group.id]),
                {"name": "Photo Group", "description": "", "image": make_image()},
            )
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertTrue(self.group.image)
        self.assertIn(f"groups/{self.group.id}/", self.group.image.name)

    def test_image_filename_uses_uuid(self):
        """The stored filename is a UUID, not the original upload name."""
        self.client.force_login(self.user)
        with override_settings(MEDIA_ROOT=self.media_dir):
            self.client.post(
                reverse("edit_group", args=[self.group.id]),
                {"name": "Photo Group", "description": "", "image": make_image("my_photo.jpg")},
            )
        self.group.refresh_from_db()
        filename = os.path.basename(self.group.image.name)
        self.assertNotEqual(filename, "my_photo.jpg")

    def test_replace_image_removes_old_file(self):
        """Uploading a new image deletes the previous file from disk."""
        self.client.force_login(self.user)
        with override_settings(MEDIA_ROOT=self.media_dir):
            self.client.post(
                reverse("edit_group", args=[self.group.id]),
                {"name": "Photo Group", "description": "", "image": make_image("first.jpg")},
            )
            self.group.refresh_from_db()
            old_path = self.group.image.path

            self.client.post(
                reverse("edit_group", args=[self.group.id]),
                {"name": "Photo Group", "description": "", "image": make_image("second.jpg")},
            )
            self.assertFalse(os.path.isfile(old_path))

        self.group.refresh_from_db()
        self.assertTrue(self.group.image)

    def test_edit_without_image_keeps_existing(self):
        """Editing name/description without a new image preserves the existing image."""
        self.client.force_login(self.user)
        with override_settings(MEDIA_ROOT=self.media_dir):
            self.client.post(
                reverse("edit_group", args=[self.group.id]),
                {"name": "Photo Group", "description": "", "image": make_image()},
            )
            self.group.refresh_from_db()
            old_image_name = self.group.image.name

            self.client.post(
                reverse("edit_group", args=[self.group.id]),
                {"name": "New Name", "description": "New desc"},
            )

        self.group.refresh_from_db()
        self.assertEqual(self.group.image.name, old_image_name)
        self.assertEqual(self.group.name, "New Name")

    def test_outsider_cannot_upload_image(self):
        """A non-member is redirected to dashboard and the group is unchanged."""
        self.client.force_login(self.outsider)
        with override_settings(MEDIA_ROOT=self.media_dir):
            response = self.client.post(
                reverse("edit_group", args=[self.group.id]),
                {"name": "Hacked", "description": "", "image": make_image()},
            )
        self.assertRedirects(response, reverse("dashboard"))
        self.group.refresh_from_db()
        self.assertFalse(self.group.image)
        self.assertEqual(self.group.name, "Photo Group")
