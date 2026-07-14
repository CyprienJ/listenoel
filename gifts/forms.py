import calendar

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils.translation import gettext as _

from .models import Group, User


class LocalUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, label="Email")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "nickname",
            "email",
        )

    def clean_nickname(self):
        return self.cleaned_data["nickname"].lower()


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ("name",)
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control rounded-pill border-0 bg-body-tertiary p-3",
                    "placeholder": "ex: Famille Smith",
                }
            ),
        }


class UserProfileForm(forms.ModelForm):
    def clean(self):
        cleaned_data = super().clean()
        month = cleaned_data.get("birthday_month")
        day = cleaned_data.get("birthday_day")
        if bool(month) != bool(day):
            raise forms.ValidationError(_("Please provide both a birthday month and day."))
        if month and day and day > calendar.monthrange(2000, month)[1]:
            self.add_error("birthday_day", _("Please enter a valid birthday."))
        return cleaned_data

    class Meta:
        model = User
        fields = ["nickname", "email", "birthday_month", "birthday_day", "avatar"]
        labels = {
            "nickname": _("Nickname"),
            "email": _("Email"),
            "birthday_month": _("Birthday month"),
            "birthday_day": _("Birthday day"),
            "avatar": _("Profile picture"),
        }
        widgets = {
            "nickname": forms.TextInput(attrs={"class": "form-control form-control-lg rounded-4 border-1"}),
            "email": forms.EmailInput(attrs={"class": "form-control form-control-lg rounded-4 border-1"}),
            "birthday_month": forms.Select(
                choices=[("", _("Month"))] + [(month, calendar.month_name[month]) for month in range(1, 13)],
                attrs={"class": "form-select form-select-lg rounded-4 border-1"},
            ),
            "birthday_day": forms.Select(
                choices=[("", _("Day"))] + [(day, day) for day in range(1, 32)],
                attrs={"class": "form-select form-select-lg rounded-4 border-1"},
            ),
        }
