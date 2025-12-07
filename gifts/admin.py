from django.contrib import admin
from .models import Family, Person, Gift, Reservation

@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ("name",)

@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ("name", "family", "password")
    list_filter = ("family",)

@admin.register(Gift)
class GiftAdmin(admin.ModelAdmin):
    list_display = ("title", "owner")

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("gift", "reserver")
