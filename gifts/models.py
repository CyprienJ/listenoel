import os
import uuid

from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
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
    is_demo = models.BooleanField(default=False)
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
    birthday_month = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
    )
    birthday_day = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
    )
    is_verified = models.BooleanField(default=False)
    is_managed = models.BooleanField(default=False)
    is_demo = models.BooleanField(default=False)
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

    @property
    def birthday(self):
        if self.birthday_month and self.birthday_day:
            return f"{self.birthday_month:02d}-{self.birthday_day:02d}"
        return None

    @birthday.setter
    def birthday(self, value):
        if not value:
            self.birthday_month = None
            self.birthday_day = None
            return
        if hasattr(value, "month") and hasattr(value, "day"):
            self.birthday_month = value.month
            self.birthday_day = value.day
            return
        month, day = str(value).split("-")[-2:]
        self.birthday_month = int(month)
        self.birthday_day = int(day)


class Subscription(models.Model):
    subscriber = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subscription_records")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="subscriber_records")
    email_enabled = models.BooleanField(default=True)
    rss_enabled = models.BooleanField(default=False)
    birthday_reminder = models.BooleanField(default=False)
    christmas_reminder = models.BooleanField(default=False)
    feed_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("subscriber", "owner"), name="unique_list_subscription"),
        ]

    def __str__(self):
        return f"{self.subscriber.nickname} → {self.owner.nickname}"


class ReminderDelivery(models.Model):
    EVENT_CHOICES = (("birthday", _("Birthday")), ("christmas", _("Christmas")))
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="reminder_deliveries")
    event = models.CharField(max_length=10, choices=EVENT_CHOICES)
    event_year = models.PositiveSmallIntegerField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("subscription", "event", "event_year"),
                name="unique_subscription_event_reminder",
            )
        ]


class Gift(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="gifts")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    url = models.URLField(blank=True, max_length=1000)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="created_gifts")
    visible_in = models.ManyToManyField(Group, related_name="visible_gifts", blank=True)
    price = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    currency = models.CharField(max_length=3, default="EUR")
    image_url = models.URLField(blank=True, max_length=1000)
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


class ExtensionAuthorizationCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="extension_authorization_codes")
    code_hash = models.CharField(max_length=64, unique=True)
    code_challenge = models.CharField(max_length=128)
    redirect_uri = models.URLField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class ExtensionAccessToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="extension_access_tokens")
    token_prefix = models.CharField(max_length=16, unique=True, db_index=True)
    token_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)


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
    MODE_WISHLIST = "wishlist"
    MODE_SECRET_SANTA = "secret_santa"
    MODE_CHOICES = (
        (MODE_WISHLIST, _("Event wishlist")),
        (MODE_SECRET_SANTA, _("Christmas / Secret Santa")),
    )

    name = models.CharField(max_length=200)
    owner = models.ForeignKey("User", on_delete=models.CASCADE, related_name="event_lists")
    description = models.TextField(blank=True)
    event_date = models.DateField(null=True, blank=True)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_WISHLIST)
    budget_max = models.DecimalField(max_digits=7, decimal_places=2, blank=True, null=True)
    is_demo = models.BooleanField(default=False)
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

    @property
    def is_secret_santa(self):
        return self.mode == self.MODE_SECRET_SANTA

    def secret_santa_participants(self):
        participant_ids = list(self.participants.values_list("id", flat=True))
        if self.owner_id not in participant_ids:
            participant_ids.append(self.owner_id)
        return User.objects.filter(id__in=participant_ids).order_by("nickname", "email")


class SecretSantaGuestParticipant(models.Model):
    event = models.ForeignKey(EventList, on_delete=models.CASCADE, related_name="secret_santa_guest_participants")
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=("event", "name"), name="unique_secret_santa_guest_participant"),
        ]

    def __str__(self):
        return f"{self.name} ({self.event.name})"


def _secret_santa_user_fk(kind, role):
    return models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name=f"secret_santa_{kind}_as_{role}",
    )


def _secret_santa_guest_fk(kind, role):
    return models.ForeignKey(
        SecretSantaGuestParticipant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name=f"secret_santa_{kind}_as_{role}",
    )


class SecretSantaParticipantPairMixin:
    @staticmethod
    def _participant_key(user_id, guest_id):
        return f"user:{user_id}" if user_id else f"guest:{guest_id}"

    @staticmethod
    def _participant_name(user, guest):
        return user.nickname if user else guest.name

    @property
    def giver_key(self):
        return self._participant_key(self.giver_id, self.giver_guest_id)

    @property
    def receiver_key(self):
        return self._participant_key(self.receiver_id, self.receiver_guest_id)

    @property
    def giver_name(self):
        return self._participant_name(self.giver, self.giver_guest)

    @property
    def receiver_name(self):
        return self._participant_name(self.receiver, self.receiver_guest)


class SecretSantaExclusion(SecretSantaParticipantPairMixin, models.Model):
    event = models.ForeignKey(EventList, on_delete=models.CASCADE, related_name="secret_santa_exclusions")
    giver = _secret_santa_user_fk("exclusions", "giver")
    receiver = _secret_santa_user_fk("exclusions", "receiver")
    giver_guest = _secret_santa_guest_fk("exclusions", "giver")
    receiver_guest = _secret_santa_guest_fk("exclusions", "receiver")
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.event.name}: {self.giver_name} !→ {self.receiver_name}"


class SecretSantaAssignment(SecretSantaParticipantPairMixin, models.Model):
    event = models.ForeignKey(EventList, on_delete=models.CASCADE, related_name="secret_santa_assignments")
    giver = _secret_santa_user_fk("assignments", "giver")
    receiver = _secret_santa_user_fk("assignments", "receiver")
    giver_guest = _secret_santa_guest_fk("assignments", "giver")
    receiver_guest = _secret_santa_guest_fk("assignments", "receiver")
    created_at = models.DateTimeField(default=timezone.now)

    @property
    def receiver_has_wish_list(self):
        return bool(self.receiver_id)

    def __str__(self):
        return f"{self.event.name}: {self.giver_name} → {self.receiver_name}"


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
