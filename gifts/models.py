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
        size=[1200, 400], crop=["middle", "center"], upload_to=get_group_image_path, quality=75, blank=True, null=True
    )
    show_history = models.BooleanField(default=False)
    show_balance = models.BooleanField(default=False)

    @property
    def has_offered_gifts(self):
        return self.reservations_group.filter(offered=True).exists()

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
    is_managed = models.BooleanField(default=False)
    managed_by = models.ForeignKey("self", on_delete=models.CASCADE, related_name="sub_accounts", blank=True, null=True)
    subscriptions = models.ManyToManyField(
        "self",
        through="Subscription",
        through_fields=("subscriber", "owner"),
        symmetrical=False,
        related_name="subscribers",
        blank=True,
    )
    avatar = ResizedImageField(
        size=[200, 200], crop=["middle", "center"], upload_to=get_avatar_path, quality=80, blank=True, null=True
    )
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def save(self, *args, **kwargs):
        self.email = self.email.lower()
        self.username = self.email
        super().save(*args, **kwargs)


class Subscription(models.Model):
    subscriber = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subscription_records")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subscriber_records")
    email_enabled = models.BooleanField(default=True)
    rss_enabled = models.BooleanField(default=False)
    feed_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("subscriber", "owner"), name="unique_list_subscription"),
        ]

    def __str__(self):
        return f"{self.subscriber.nickname} → {self.owner.nickname}"


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
    actual_cost = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    expense_split = models.ManyToManyField("User", related_name="split_gifts", blank=True)
    group_reserved_on = models.ForeignKey(
        Group, blank=True, null=True, on_delete=models.SET_NULL, related_name="reservations_group"
    )
    managed_member = models.ForeignKey(
        "ManagedMember", blank=True, null=True, on_delete=models.CASCADE, related_name="gifts"
    )
    event_list = models.ForeignKey("EventList", blank=True, null=True, on_delete=models.CASCADE, related_name="gifts")
    is_hidden = models.BooleanField(default=False)

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


MANAGED_MEMBER_COLORS = [
    "oklch(60% 0.14 100)",
    "oklch(60% 0.14 180)",
    "oklch(60% 0.14 230)",
    "oklch(60% 0.14 290)",
    "oklch(60% 0.14 340)",
]


class ManagedMember(models.Model):
    name = models.CharField(max_length=100)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="managed_members")
    color = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.OneToOneField(
        "User", on_delete=models.CASCADE, null=True, blank=True, related_name="managed_member_profile"
    )

    def __str__(self):
        return f"{self.name} ({self.group.name})"


class BalanceSettlement(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="balance_settlements")
    payer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="settlements_made")
    payee = models.ForeignKey(User, on_delete=models.CASCADE, related_name="settlements_received")
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    created_at = models.DateTimeField(default=timezone.now)


def get_event_image_path(instance, filename):
    ext = filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join("events", str(instance.id), filename)


class EventList(models.Model):
    name = models.CharField(max_length=200)
    owner = models.ForeignKey("User", on_delete=models.CASCADE, related_name="event_lists")
    description = models.TextField(blank=True)
    event_date = models.DateField(null=True, blank=True)
    image = ResizedImageField(
        size=[1200, 400], crop=["middle", "center"], upload_to=get_event_image_path, quality=75, blank=True, null=True
    )
    access_token = models.CharField(max_length=12, unique=True, blank=True)
    participants = models.ManyToManyField("User", blank=True, related_name="participating_event_lists")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.access_token:
            self.access_token = uuid.uuid4().hex[:8].upper()
        super().save(*args, **kwargs)


class GuestReservation(models.Model):
    gift = models.ForeignKey("Gift", on_delete=models.CASCADE, related_name="guest_reservations")
    reserver_user = models.ForeignKey(
        "User", on_delete=models.SET_NULL, null=True, blank=True, related_name="event_reservations"
    )
    reserver_name = models.CharField(max_length=100)
    session_key = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    exclusivity = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["gift", "reserver_user"],
                condition=models.Q(reserver_user__isnull=False),
                name="unique_user_event_reservation",
            )
        ]

    def __str__(self):
        return f"{self.reserver_name} → {self.gift.title}"
