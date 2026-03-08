from datetime import timedelta

from django.core import mail
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import Gift, Group, User


class UserCleanupTest(TestCase):
    def test_cleanup_unverified_users_command(self):
        # Create a verified user
        User.objects.create_user(
            username='verified@test.com',
            email='verified@test.com',
            password='password123',
            is_verified=True
        )
        
        # Create an unverified user (recent)
        User.objects.create_user(
            username='recent@test.com',
            email='recent@test.com',
            password='password123',
            is_verified=False
        )
        
        # Create an unverified user (old)
        old_user = User.objects.create_user(
            username='old@test.com',
            email='old@test.com',
            password='password123',
            is_verified=False
        )
        # Manually set date_joined to 31 minutes ago
        old_user.date_joined = timezone.now() - timedelta(minutes=31)
        old_user.save()
        
        # Run command
        call_command('cleanup_unverified_users')
        
        # Check results
        self.assertTrue(User.objects.filter(email='verified@test.com').exists())
        self.assertTrue(User.objects.filter(email='recent@test.com').exists())
        self.assertFalse(User.objects.filter(email='old@test.com').exists())

    def test_cleanup_in_view(self):
        # Create an unverified user (old)
        old_user = User.objects.create_user(
            username='old_view@test.com',
            email='old_view@test.com',
            password='password123',
            is_verified=False
        )
        old_user.date_joined = timezone.now() - timedelta(minutes=31)
        old_user.save()
        
        # Using reverse to be sure about the URL
        self.client.get(reverse('register'))
        
        self.assertFalse(User.objects.filter(email='old_view@test.com').exists())

class AccessControlTest(TestCase):
    def setUp(self):
        self.unverified_user = User.objects.create_user(
            username='unverified@test.com',
            email='unverified@test.com',
            password='password123',
            is_verified=False,
            nickname='Unverified'
        )
        self.verified_user = User.objects.create_user(
            username='verified@test.com',
            email='verified@test.com',
            password='password123',
            is_verified=True,
            nickname='Verified'
        )

    def test_anonymous_access(self):
        """
        Test access for an unauthenticated user.
        - login/register : OK (200)
        - welcome : OK (200)
        - dashboard/profile/etc : Redirect to login (302)
        """
        # OK
        self.assertEqual(self.client.get(reverse('login')).status_code, 200)
        self.assertEqual(self.client.get(reverse('register')).status_code, 200)
        self.assertEqual(self.client.get(reverse('welcome')).status_code, 200)

        # Redirect to login by @login_required
        protected_urls = [
            reverse('dashboard'),
            reverse('profile'),
            reverse('create_group'),
        ]
        for url in protected_urls:
            response = self.client.get(url)
            self.assertRedirects(response, reverse('login') + f"?next={url}")

    def test_unverified_user_access(self):
        """
        Test access for a logged-in but unverified user.
        - login : OK (200)
        - register : Redirect to verify_email_sent (302)
        - welcome : Redirect to verify_email_sent (302)
        - verify_email_sent/resend/profile/logout : OK (200 or 302 depending on action)
        - dashboard/groups/etc : Redirect to verify_email_sent (302) via middleware
        """
        self.client.force_login(self.unverified_user)

        # Django's LoginView does not automatically redirect if accessed via GET while already logged in
        self.assertEqual(self.client.get(reverse('login')).status_code, 200)
        
        # register is redirected by middleware (as it is not in allowed_urls)
        self.assertRedirects(self.client.get(reverse('register')), reverse('verify_email_sent'))
        
        # welcome redirects directly to verify_email_sent for unverified users
        self.assertRedirects(self.client.get(reverse('welcome')), reverse('verify_email_sent'))

        # Authorized access for unverified users
        self.assertEqual(self.client.get(reverse('verify_email_sent')).status_code, 200)
        self.assertEqual(self.client.get(reverse('profile')).status_code, 200)

        # URLs blocked by middleware and redirected to verify_email_sent
        self.assertRedirects(self.client.get(reverse('dashboard')), reverse('verify_email_sent'))

    def test_verified_user_access(self):
        """
        Test access for a logged-in and verified user.
        - login/register/welcome : Redirect to dashboard (302)
        - verify_email_sent/resend : Redirect to dashboard (302) (since already verified)
        - dashboard/profile/groups/etc : OK (200)
        """
        self.client.force_login(self.verified_user)

        # Redirect to dashboard
        self.assertEqual(self.client.get(reverse('login')).status_code, 200)
        self.assertRedirects(self.client.get(reverse('register')), reverse('dashboard'))
        self.assertRedirects(self.client.get(reverse('welcome')), reverse('dashboard'))

        # Redirect to dashboard as already verified
        self.assertRedirects(self.client.get(reverse('verify_email_sent')), reverse('dashboard'))
        self.assertRedirects(self.client.get(reverse('resend_verification')), reverse('dashboard'))

        # Authorized access
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)
        self.assertEqual(self.client.get(reverse('profile')).status_code, 200)
        
        # For @require_POST views, we just test that we are not redirected by the middleware
        # (thus 405 instead of 302 to verify_email_sent)
        self.assertEqual(self.client.get(reverse('create_group')).status_code, 405)

class PasswordResetTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser@example.com',
            email='testuser@example.com',
            password='oldpassword123',
            is_verified=True,
            nickname='TestUser'
        )

    def test_password_reset_flow(self):
        # 1. Reset request
        response = self.client.post(reverse('password_reset'), {'email': 'testuser@example.com'})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('password_reset_done'))
        
        # Verify that an email was sent
        self.assertEqual(len(mail.outbox), 1)
        reset_mail = mail.outbox[0]
        self.assertIn('testuser@example.com', reset_mail.to)
        
        # Verify that the email contains HTML (since we configured html_email_template_name)
        self.assertTrue(any(alt[1] == 'text/html' for alt in reset_mail.alternatives))
        
        # 2. Verify access to password_reset_done
        response = self.client.get(reverse('password_reset_done'))
        self.assertEqual(response.status_code, 200)

    def test_password_reset_unverified_user(self):
        self.user.is_verified = False
        self.user.save()
        
        self.client.force_login(self.user)
        # Should not be redirected to verify_email_sent by the middleware
        response = self.client.get(reverse('password_reset'))
        self.assertEqual(response.status_code, 200)

    def test_password_reset_confirm_unverified_user(self):
        self.user.is_verified = False
        self.user.save()
        
        url = reverse('password_reset_confirm', kwargs={'uidb64': 'MQ', 'token': 'abc-123'})
        
        self.client.force_login(self.user)
        # Should not be redirected to verify_email_sent by the middleware
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

class GiftAccessControlTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='user1@test.com',
            email='user1@test.com',
            password='password',
            is_verified=True,
            nickname='User1')
        self.user2 = User.objects.create_user(
            username='user2@test.com',
            email='user2@test.com',
            password='password',
            is_verified=True,
            nickname='User2')
        self.user3 = User.objects.create_user(
            username='user3@test.com',
            email='user3@test.com',
            password='password',
            is_verified=True,
            nickname='User3')

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
        self.assertEqual(self.client.get(reverse('view_list', args=[self.user1.id])).status_code, 200)
        
        self.client.force_login(self.user3)
        # User3 does not share a group with User1
        self.assertEqual(self.client.get(reverse('view_list', args=[self.user1.id])).status_code, 403)

    def test_edit_gift_access(self):
        """A user can only edit his gifts or surprises from groups he is in"""
        # User1 edits his own gift
        self.client.force_login(self.user1)
        response = self.client.post(reverse('edit_gift', args=[self.gift_user1.id]), {'title': 'Updated Title'})
        self.assertEqual(response.status_code, 302)
        self.gift_user1.refresh_from_db()
        self.assertEqual(self.gift_user1.title, 'Updated Title')

        # User2 edits the surprise he created for User1
        self.client.force_login(self.user2)
        response = self.client.post(reverse('edit_gift', args=[self.surprise_user1.id]), {'title': 'Updated Surprise'})
        self.assertEqual(response.status_code, 302)
        self.surprise_user1.refresh_from_db()
        self.assertEqual(self.surprise_user1.title, 'Updated Surprise')

        # User3 attempts to edit User1's gift (should fail)
        self.client.force_login(self.user3)
        response = self.client.post(reverse('edit_gift', args=[self.gift_user1.id]), {'title': 'Hacked Title'})
        # Currently this probably passes (200 or 302), we expect 403 or 404
        self.assertIn(response.status_code, [403, 404])

    def test_delete_gift_access(self):
        """A user can only delete his gifts or surprises from groups he is in"""
        # User3 attempts to delete User1's gift
        self.client.force_login(self.user3)
        response = self.client.post(reverse('delete_gift', args=[self.gift_user1.id]))
        self.assertIn(response.status_code, [403, 404])
        self.assertTrue(Gift.objects.filter(id=self.gift_user1.id).exists())

class SubscriptionTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='user1@test.com',
            email='user1@test.com',
            password='password',
            is_verified=True,
            nickname='User1')
        self.user2 = User.objects.create_user(
            username='user2@test.com',
            email='user2@test.com',
            password='password',
            is_verified=True,
            nickname='User2')
        self.user3 = User.objects.create_user(
            username='user3@test.com',
            email='user3@test.com',
            password='password',
            is_verified=True,
            nickname='User3')
        
        self.group = Group.objects.create(name="Group 1-2")
        self.group.members.add(self.user1, self.user2)

    def test_toggle_subscription(self):
        self.client.force_login(self.user2)
        # Subscribe
        response = self.client.post(reverse('toggle_subscription', args=[self.user1.id]))
        self.assertRedirects(response, reverse('view_list', args=[self.user1.id]))
        self.assertTrue(self.user2.subscriptions.filter(id=self.user1.id).exists())
        
        # Unsubscribe
        response = self.client.post(reverse('toggle_subscription', args=[self.user1.id]))
        self.assertRedirects(response, reverse('view_list', args=[self.user1.id]))
        self.assertFalse(self.user2.subscriptions.filter(id=self.user1.id).exists())

    def test_subscribe_self(self):
        self.client.force_login(self.user1)
        response = self.client.post(reverse('toggle_subscription', args=[self.user1.id]))
        self.assertEqual(response.status_code, 403)

    def test_subscribe_no_common_group(self):
        self.client.force_login(self.user3)
        response = self.client.post(reverse('toggle_subscription', args=[self.user1.id]))
        self.assertEqual(response.status_code, 403)

    def test_notification_sent_on_add_gift(self):
        # User2 subscribes to User1
        self.user2.subscriptions.add(self.user1)
        
        self.client.force_login(self.user1)
        # User1 adds a gift to his own list
        response = self.client.post(reverse('add_gift', args=[self.user1.id]), {
            'title': 'New Gift',
            'description': 'A cool gift',
            'url': 'http://example.com'
        })
        self.assertRedirects(response, reverse('view_list', args=[self.user1.id]))
        
        # Verify email delivery
        self.assertEqual(len(mail.outbox), 1)
        notification_mail = mail.outbox[0]
        self.assertIn(self.user2.email, notification_mail.to)
        # The subject is translated to French by default in tests because LANGUAGE_CODE='fr'
        self.assertIn('User1', notification_mail.subject)
        self.assertIn('New Gift', notification_mail.body)
        self.assertIn('A cool gift', notification_mail.body)
        self.assertIn('http://example.com', notification_mail.body)
        
        # Verify unsubscribe link
        self.assertIn('/unsubscribe/', notification_mail.body)

    def test_unsubscribe_token(self):
        self.user2.subscriptions.add(self.user1)
        
        uid = urlsafe_base64_encode(force_bytes(self.user1.pk))
        token = "dummy-token"
        url = reverse('unsubscribe_token', args=[uid, token])
        
        self.client.force_login(self.user2)
        # Test with GET because button changed to link
        response = self.client.get(url)
        self.assertRedirects(response, reverse('view_list', args=[self.user1.id]))
        self.assertFalse(self.user2.subscriptions.filter(id=self.user1.id).exists())

    def test_no_notification_if_not_owner_adding(self):
        # User2 subscribes to User1
        self.user2.subscriptions.add(self.user1)
        
        self.client.force_login(self.user2)
        # User2 add a surprise to User1's list
        self.client.post(reverse('add_gift', args=[self.user1.id]), {'title': 'Surprise'})
        
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
        self.client.post(reverse('add_gift', args=[self.user1.id]), {
            'title': 'Secret Gift',
            'visible_in': [group2.id]
        })
        
        # User2 shouldn't receive a notification
        self.assertEqual(len(mail.outbox), 0)
        
        # User3 subscribes to User1
        self.user3.subscriptions.add(self.user1)
        mail.outbox = []
        
        # User1 add a gift visible to everybody
        self.client.post(reverse('add_gift', args=[self.user1.id]), {'title': 'Public Gift'})
        
        # User2 and User3 receive a mail
        self.assertEqual(len(mail.outbox), 2)

    def test_add_gift_access(self):
        """Add a gift/surprise only if there is a common group"""
        self.client.force_login(self.user3)
        # User3 attempts to add a gift to User1
        response = self.client.post(reverse('add_gift', args=[self.user1.id]), {'title': 'Bad Surprise'})
        self.assertIn(response.status_code, [403, 404])
        self.assertFalse(Gift.objects.filter(title='Bad Surprise').exists())

class ReservationSharingTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='user1@test.com',
            email='user1@test.com',
            password='password',
            is_verified=True,
            nickname='User1')
        self.user2 = User.objects.create_user(
            username='user2@test.com',
            email='user2@test.com',
            password='password',
            is_verified=True,
            nickname='User2')
        self.user3 = User.objects.create_user(
            username='user3@test.com',
            email='user3@test.com',
            password='password',
            is_verified=True,
            nickname='User3')

        self.group = Group.objects.create(name="Group 1-2-3")
        self.group.members.add(self.user1, self.user2, self.user3)

        self.gift = Gift.objects.create(owner=self.user1, title="Shared Gift", price=100)

class GroupManagementTest(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(
            username='creator@test.com',
            email='creator@test.com',
            password='password',
            is_verified=True,
            nickname='Creator')
        self.member = User.objects.create_user(
            username='member@test.com',
            email='member@test.com',
            password='password',
            is_verified=True,
            nickname='Member')
        self.outsider = User.objects.create_user(
            username='outsider@test.com',
            email='outsider@test.com',
            password='password',
            is_verified=True,
            nickname='Outsider')

        self.group = Group.objects.create(name="Original Name", created_by=self.creator)
        self.group.members.add(self.creator, self.member)
        self.original_token = self.group.invite_token

    def test_edit_group_name_as_creator(self):
        self.client.force_login(self.creator)
        response = self.client.post(reverse('edit_group', args=[self.group.id]), {'name': 'New Name'})
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, 'New Name')

    def test_edit_group_name_as_member(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse('edit_group', args=[self.group.id]), {'name': 'New Name'})
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, 'New Name')

    def test_regenerate_token_as_creator(self):
        self.client.force_login(self.creator)
        response = self.client.post(reverse('regenerate_group_token', args=[self.group.id]))
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertNotEqual(self.group.invite_token, self.original_token)
        self.assertTrue(len(self.group.invite_token) > 0)

    def test_regenerate_token_as_member(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse('regenerate_group_token', args=[self.group.id]))
        self.assertEqual(response.status_code, 302)
        self.group.refresh_from_db()
        self.assertNotEqual(self.group.invite_token, self.original_token)
        self.assertTrue(len(self.group.invite_token) > 0)
