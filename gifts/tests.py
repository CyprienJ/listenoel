from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from django.core.management import call_command
from django.urls import reverse
from .models import User, Group, Gift, Reservation

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
        Test des accès pour un utilisateur non connecté.
        - login/register : OK (200)
        - welcome : OK (200)
        - dashboard/profile/etc : Redirection vers login (302)
        """
        # OK
        self.assertEqual(self.client.get(reverse('login')).status_code, 200)
        self.assertEqual(self.client.get(reverse('register')).status_code, 200)
        self.assertEqual(self.client.get(reverse('welcome')).status_code, 200)

        # Redirection vers login par @login_required
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
        Test des accès pour un utilisateur connecté mais non vérifié.
        - login : OK (200)
        - register : Redirection vers verify_email_sent (302)
        - welcome : Redirection vers verify_email_sent (302)
        - verify_email_sent/resend/profile/logout : OK (200 ou 302 selon action)
        - dashboard/groupes/etc : Redirection vers verify_email_sent (302) par middleware
        """
        self.client.force_login(self.unverified_user)

        # La LoginView de Django ne redirige pas automatiquement si on y accède en GET en étant déjà connecté
        self.assertEqual(self.client.get(reverse('login')).status_code, 200)
        
        # register est redirigé par le middleware (car non dans allowed_urls)
        self.assertRedirects(self.client.get(reverse('register')), reverse('verify_email_sent'))
        
        # welcome redirige directement vers verify_email_sent pour les non-vérifiés
        self.assertRedirects(self.client.get(reverse('welcome')), reverse('verify_email_sent'))

        # Accès autorisés pour non vérifiés
        self.assertEqual(self.client.get(reverse('verify_email_sent')).status_code, 200)
        self.assertEqual(self.client.get(reverse('profile')).status_code, 200)

        # URLs bloquées par le middleware et redirigées vers verify_email_sent
        self.assertRedirects(self.client.get(reverse('dashboard')), reverse('verify_email_sent'))

    def test_verified_user_access(self):
        """
        Test des accès pour un utilisateur connecté et vérifié.
        - login/register/welcome : Redirection vers dashboard (302)
        - verify_email_sent/resend : Redirection vers dashboard (302) (car déjà vérifié)
        - dashboard/profile/groupes/etc : OK (200)
        """
        self.client.force_login(self.verified_user)

        # Redirection vers dashboard
        self.assertEqual(self.client.get(reverse('login')).status_code, 200)
        self.assertRedirects(self.client.get(reverse('register')), reverse('dashboard'))
        self.assertRedirects(self.client.get(reverse('welcome')), reverse('dashboard'))

        # Redirection vers dashboard car déjà vérifié
        self.assertRedirects(self.client.get(reverse('verify_email_sent')), reverse('dashboard'))
        self.assertRedirects(self.client.get(reverse('resend_verification')), reverse('dashboard'))

        # Accès autorisés
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 200)
        self.assertEqual(self.client.get(reverse('profile')).status_code, 200)
        
        # Pour les vues @require_POST, on teste juste qu'on n'est pas redirigé par le middleware (donc 405 au lieu de 302 vers verify_email_sent)
        self.assertEqual(self.client.get(reverse('create_group')).status_code, 405)

class GiftAccessControlTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1@test.com', email='user1@test.com', password='password', is_verified=True, nickname='User1')
        self.user2 = User.objects.create_user(username='user2@test.com', email='user2@test.com', password='password', is_verified=True, nickname='User2')
        self.user3 = User.objects.create_user(username='user3@test.com', email='user3@test.com', password='password', is_verified=True, nickname='User3')

        # Groupe entre User1 et User2
        self.group = Group.objects.create(name="Group 1-2")
        self.group.members.add(self.user1, self.user2)

        # Cadeau de User1 (qu'il a créé lui-même)
        self.gift_user1 = Gift.objects.create(owner=self.user1, created_by=self.user1, title="Gift User1")
        
        # Surprise pour User1 créée par User2
        self.surprise_user1 = Gift.objects.create(owner=self.user1, created_by=self.user2, title="Surprise User1")

    def test_view_list_access(self):
        """Un utilisateur ne peut accéder aux listes que de lui ou des gens avec qui il a au moins un groupe en commun"""
        self.client.force_login(self.user2)
        # User2 partage un groupe avec User1
        self.assertEqual(self.client.get(reverse('view_list', args=[self.user1.id])).status_code, 200)
        
        self.client.force_login(self.user3)
        # User3 ne partage pas de groupe avec User1
        self.assertEqual(self.client.get(reverse('view_list', args=[self.user1.id])).status_code, 403)

    def test_edit_gift_access(self):
        """Un utilisateur ne puisse modifier que ses cadeaux ou les surprises des groupes dans lesquels il est"""
        # User1 modifie son propre cadeau
        self.client.force_login(self.user1)
        response = self.client.post(reverse('edit_gift', args=[self.gift_user1.id]), {'title': 'Updated Title'})
        self.assertEqual(response.status_code, 302)
        self.gift_user1.refresh_from_db()
        self.assertEqual(self.gift_user1.title, 'Updated Title')

        # User2 modifie la surprise qu'il a créée pour User1
        self.client.force_login(self.user2)
        response = self.client.post(reverse('edit_gift', args=[self.surprise_user1.id]), {'title': 'Updated Surprise'})
        self.assertEqual(response.status_code, 302)
        self.surprise_user1.refresh_from_db()
        self.assertEqual(self.surprise_user1.title, 'Updated Surprise')

        # User3 tente de modifier le cadeau de User1 (doit échouer)
        self.client.force_login(self.user3)
        response = self.client.post(reverse('edit_gift', args=[self.gift_user1.id]), {'title': 'Hacked Title'})
        # Actuellement ça passe probablement (200 ou 302), on s'attend à 403 ou 404
        self.assertIn(response.status_code, [403, 404])

    def test_delete_gift_access(self):
        """Un utilisateur ne puisse supprimer que ses cadeaux ou les surprises des groupes dans lesquels il est"""
        # User3 tente de supprimer le cadeau de User1
        self.client.force_login(self.user3)
        response = self.client.post(reverse('delete_gift', args=[self.gift_user1.id]))
        self.assertIn(response.status_code, [403, 404])
        self.assertTrue(Gift.objects.filter(id=self.gift_user1.id).exists())

    def test_reserve_gift_access(self):
        """Ne puisse s'attribuer un cadeau d'un groupe sur lequel il n'est pas"""
        self.client.force_login(self.user3)
        response = self.client.post(reverse('reserve_gift', args=[self.gift_user1.id]))
        self.assertIn(response.status_code, [403, 404])

    def test_unreserve_gift_access(self):
        """Ne puisse unreserve que un cadeau qu'il a reservé lui même"""
        # User2 réserve le cadeau de User1
        Reservation.objects.create(gift=self.gift_user1, reserver=self.user2)
        
        # User3 tente de déréserver
        self.client.force_login(self.user3)
        response = self.client.post(reverse('unreserve_gift', args=[self.gift_user1.id]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Reservation.objects.filter(gift=self.gift_user1).exists())

    def test_add_gift_access(self):
        """Ajouter un cadeau/surprise seulement si groupe en commun"""
        self.client.force_login(self.user3)
        # User3 tente d'ajouter un cadeau à User1
        response = self.client.post(reverse('add_gift', args=[self.user1.id]), {'title': 'Bad Surprise'})
        self.assertIn(response.status_code, [403, 404])
        self.assertFalse(Gift.objects.filter(title='Bad Surprise').exists())

class GroupManagementTest(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(username='creator@test.com', email='creator@test.com', password='password', is_verified=True, nickname='Creator')
        self.member = User.objects.create_user(username='member@test.com', email='member@test.com', password='password', is_verified=True, nickname='Member')
        self.outsider = User.objects.create_user(username='outsider@test.com', email='outsider@test.com', password='password', is_verified=True, nickname='Outsider')

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