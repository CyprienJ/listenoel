from django.db import models
from django.utils import timezone

class Family(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name

class Person(models.Model):
    name = models.CharField(max_length=100)
    password = models.CharField(max_length=100)
    family = models.ForeignKey(Family, on_delete=models.CASCADE, related_name="members")

    def __str__(self):
        return f"{self.name} ({self.family.name})"



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
