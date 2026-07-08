from django.urls import path

from . import extension_api

urlpatterns = [
    path("extension/authorize/", extension_api.extension_authorize, name="extension_authorize"),
    path("extension/privacy/", extension_api.extension_privacy, name="extension_privacy"),
    path("api/extension/token/", extension_api.extension_token, name="extension_token"),
    path("api/extension/me/", extension_api.extension_me, name="extension_me"),
    path("api/extension/quick-add/", extension_api.extension_quick_add, name="extension_quick_add"),
    path("api/extension/revoke/", extension_api.extension_revoke, name="extension_revoke"),
]
