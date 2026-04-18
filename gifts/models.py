import os
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_resized import ResizedImageField


def get_group_image_path(instance, filename):
    ext = filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join("groups", str(instance.id), filename)


def get_avatar_path(instance, filename):
    ext = filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join("profiles", str(instance.id), filename)


class Group(models.Model):
    name = models.CharField(max_length=100)
    members = models.ManyToManyField("User", related_name="gift_groups")
    group_token = models.CharField(max_length=12, unique=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey("User", on_delete=models.SET_NULL, null=True, related_name="owned_groups")
    description = models.TextField(blank=True)
    image = ResizedImageField(
        size=[800, 600], crop=["middle", "center"], upload_to=get_group_image_path, quality=75, blank=True, null=True
    )
    show_history = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.group_token:
            self.group_token = uuid.uuid4().hex[:8].upper()

        super().save(*args, **kwargs)


class User(AbstractUser):
    email = models.EmailField(
        unique=True,
        blank=False,
        error_messages={
            "unique": _("A user with that email already exists."),
        },
    )

    nickname = models.CharField(max_length=150, blank=False)
    is_verified = models.BooleanField(default=False)
    subscriptions = models.ManyToManyField("self", symmetrical=False, related_name="subscribers", blank=True)
    avatar = ResizedImageField(
        size=[200, 200], crop=["middle", "center"], upload_to=get_avatar_path, quality=80, blank=True, null=True
    )
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

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
    price = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    offered = models.BooleanField(default=False)
    offered_at = models.DateTimeField(null=True, blank=True)
    group_reserved_on = models.ForeignKey(
        Group, blank=True, null=True, on_delete=models.SET_NULL, related_name="reservations_group"
    )

    def __str__(self):
        return f"{self.title} ({self.owner.nickname})"

    def save(self, *args, **kwargs):
        try:
            if not self.created_by:
                self.created_by = self.owner
        except User.DoesNotExist:
            self.created_by = self.owner
        super().save(*args, **kwargs)


class Reservation(models.Model):
    gift = models.ForeignKey(Gift, on_delete=models.CASCADE, related_name="reservation")
    reserver = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reservations")
    created_at = models.DateTimeField(default=timezone.now)
    exclusivity = models.BooleanField(default=False)
    amount_paid = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
