import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Group(models.Model):
    name = models.CharField(max_length=100)
    members = models.ManyToManyField("User", related_name="gift_groups")
    invite_token = models.CharField(max_length=12, unique=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey("User", on_delete=models.SET_NULL, null=True, related_name="owned_groups")

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.invite_token:
            self.invite_token = uuid.uuid4().hex[:8].upper()

        super().save(*args, **kwargs)


class User(AbstractUser):
    email = models.EmailField(
        unique=True,
        blank=False,
        error_messages={
            'unique': _("A user with that email already exists."),
        }
    )

    nickname = models.CharField(max_length=150, blank=False)
    is_verified = models.BooleanField(default=False)
    subscriptions = models.ManyToManyField(
        'self',
        symmetrical=False,
        related_name='subscribers',
        blank=True
    )
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']


    def save(self, *args, **kwargs):
            self.email = self.email.lower()
            self.username = self.email
            super().save(*args, **kwargs)

class Gift(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="gifts")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    url = models.URLField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_gifts")
    visible_in = models.ManyToManyField(Group, related_name="visible_gifts", blank=True)

    def __str__(self):
        return f"{self.title} ({self.owner.nickname})"

    def save(self, *args, **kwargs):
        if not self.created_by:
            self.created_by = self.owner
        super().save(*args, **kwargs)


class Reservation(models.Model):
    gift = models.OneToOneField(Gift, on_delete=models.CASCADE, related_name="reservation")
    reserver = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reservations")
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.reserver.nickname} -> {self.gift.title}"
