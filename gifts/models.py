from django.contrib.auth.hashers import make_password, check_password
from django.db import models
from django.utils import timezone

class Group(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Person(models.Model):
    name = models.CharField(max_length=100)
    password = models.CharField(max_length=128)
    group = models.ForeignKey(Group, on_delete=models.CASCADE, related_name="members")

    def set_password(self, raw_password):
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def __str__(self):
        return f"{self.name} ({self.group.name})"



class Gift(models.Model):
    owner = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="gifts")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    url = models.URLField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.title} ({self.owner.name})"


class Reservation(models.Model):
    gift = models.OneToOneField(Gift, on_delete=models.CASCADE, related_name="reservation")
    reserver = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="reservations")
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.reserver.name} -> {self.gift.title}"
