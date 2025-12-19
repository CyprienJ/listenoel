from django.contrib import admin
from .models import Group, User, Gift, Reservation
from django import forms

class UserAdminForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False)

    class Meta:
        model = User
        fields = '__all__'

@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name",)

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    form = UserAdminForm
    list_display = ("pseudo", "group", "password")
    list_filter = ("group",)
    def save_model(self, request, obj, form, change):
        if form.cleaned_data.get('password'):
            obj.set_password(form.cleaned_data['password'])
        super().save_model(request, obj, form, change)

@admin.register(Gift)
class GiftAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "created_by")

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("gift", "reserver")
