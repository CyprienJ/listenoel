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
                attrs={"class": "form-control rounded-pill border-0 bg-light p-3", "placeholder": "ex: Famille Smith"}
            ),
        }


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["nickname", "email"]
        labels = {
            "nickname": _("Nickname"),
            "email": _("Email"),
        }
