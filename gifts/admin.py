from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Group, User, Gift, Reservation
from django.utils.translation import gettext as _

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "nickname", "email", "is_staff", "is_active", "is_verified")
    search_fields = ("username", "nickname", "email")
    ordering = ("username",)

    fieldsets = BaseUserAdmin.fieldsets + (
        (_("More information"), {"fields": ("nickname",)}),
    )

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "member_count")
    filter_horizontal = ("members",)

    def member_count(self, obj):
        return obj.members.count()
    member_count.short_description = "Nombre de membres"

@admin.register(Gift)
class GiftAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "created_by", "created_at")
    list_filter = ("owner", "created_by")
    search_fields = ("title", "description")

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("gift", "reserver", "created_at")
    list_filter = ("reserver",)