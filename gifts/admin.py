from django.contrib import admin
from .models import Family, Person, Gift, Reservation
from django import forms

class PersonAdminForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False)

    class Meta:
        model = Person
        fields = '__all__'

@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ("name",)

@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    form = PersonAdminForm
    list_display = ("name", "family", "password")
    list_filter = ("family",)
    def save_model(self, request, obj, form, change):
        if form.cleaned_data.get('password'):
            obj.set_password(form.cleaned_data['password'])
        super().save_model(request, obj, form, change)

@admin.register(Gift)
class GiftAdmin(admin.ModelAdmin):
    list_display = ("title", "owner")

@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("gift", "reserver")
