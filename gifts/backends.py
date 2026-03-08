from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class CaseInsensitiveModelBackend(ModelBackend):
    def authenticate(self, request, email=None, password=None, **kwargs):
        user_model = get_user_model()
        if email is None:
            email = kwargs.get(user_model.USERNAME_FIELD)
        try:
            user = user_model.objects.get(**{f"{user_model.USERNAME_FIELD}__iexact": email})
        except user_model.DoesNotExist:
            return None
        else:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user
