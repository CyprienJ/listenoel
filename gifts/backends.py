from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

class CaseInsensitiveModelBackend(ModelBackend):
    def authenticate(self, request, email=None, password=None, **kwargs):
        UserModel = get_user_model()
        if email is None:
            email = kwargs.get(UserModel.USERNAME_FIELD)
        try:
            user = UserModel.objects.get(**{f"{UserModel.USERNAME_FIELD}__iexact": email})
        except UserModel.DoesNotExist:
            return None
        else:
            if user.check_password(password) and self.user_can_authenticate(user):
                return user