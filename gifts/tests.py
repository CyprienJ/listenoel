from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from django.core.management import call_command
from .models import User

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
        from django.urls import reverse
        self.client.get(reverse('register'))
        
        self.assertFalse(User.objects.filter(email='old_view@test.com').exists())
