from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import account, groups, views

urlpatterns = [
    # Default
    path("", views.welcome, name="welcome"),
    path("dashboard/", views.dashboard, name="dashboard"),
    # Auth
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="welcome"), name="logout"),
    # Settings
    path("register/", account.register, name="register"),
    path(
        "account/change_password/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/change_password.html", success_url="/account/"
        ),
        name="account/change_password/",
    ),
    path("account/", account.account, name="account"),
    path("account/delete/", account.delete_account, name="delete_account"),
    path("account/verify-email/", account.verify_email_sent, name="verify_email_sent"),
    path("account/verify-email/confirm/<uidb64>/<token>/", account.verify_email_confirm, name="verify_email_confirm"),
    path("account/verify-email/resend/", account.resend_verification, name="resend_verification"),
    path(
        "account/password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="emails/password_reset_email.txt",
            html_email_template_name="emails/password_reset_email.html",
            success_url=reverse_lazy("account/password_reset_done"),
        ),
        name="account/password_reset",
    ),
    path(
        "account/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="registration/password_reset_done.html"),
        name="account/password_reset_done",
    ),
    path(
        "account/password-reset-confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url=reverse_lazy("account/password_reset_complete"),
        ),
        name="account/password_reset_confirm",
    ),
    path(
        "account/password-reset-complete/",
        auth_views.PasswordResetCompleteView.as_view(template_name="registration/password_reset_complete.html"),
        name="account/password_reset_complete",
    ),
    # Groups
    path("group/create/", groups.create_group, name="create_group"),
    path("group/join/", groups.join_group, name="join_group"),
    path("group/join/<str:token>/", groups.join_group, name="join_group"),
    path("group/join/<str:token>/confirm/", groups.join_group_confirm, name="join_group_confirm"),
    path("group/<int:group_id>/", groups.group_detail, name="group_detail"),
    path("group/<int:group_id>/edit/", groups.edit_group, name="edit_group"),
    path("group/<int:group_id>/regenerate-token/", groups.regenerate_group_token, name="regenerate_group_token"),
    path("group/<int:group_id>/leave/", groups.leave_group, name="leave_group"),
    # List
    path("list/<int:user_id>/", views.view_list, name="view_list"),
    path("add-gift/<int:owner_id>/", views.add_gift, name="add_gift"),
    path("edit-gift/<int:gift_id>/", views.edit_gift, name="edit_gift"),
    path("delete-gift/<int:gift_id>/", views.delete_gift, name="delete_gift"),
    path("gift/<int:gift_id>/reserve/", views.reserve_gift, name="reserve_gift"),
    path("gift/<int:gift_id>/modify_reservation/", views.modify_reservation, name="modify_reservation"),
    path("gift/<int:gift_id>/delete_reservation/", views.delete_reservation, name="delete_reservation"),
    path("gift/<int:gift_id>/edit-price/", views.edit_gift_price, name="edit_gift_price"),
    path("gift/<int:gift_id>/offer/", views.offer_gift, name="offer_gift"),
    path("gift/<int:gift_id>/un-offer/", views.un_offer_gift, name="un_offer_gift"),
    path("gift/<int:gift_id>/delete-offered/", views.delete_offered_gift, name="delete_offered_gift"),
    path("gift/<int:gift_id>/edit-offered-amounts/", views.edit_offered_amounts, name="edit_offered_amounts"),
    path("history/", views.history_view, name="history"),
    path("history/<int:group_id>/", views.history_view, name="history_group"),
    path("gift/<int:gift_id>/mark-received/", views.mark_received, name="mark_received"),
    # Notification
    path("subscribe/<int:user_id>/", views.toggle_subscription, name="toggle_subscription"),
    path("unsubscribe/<uidb64>/<token>/", views.unsubscribe_token, name="unsubscribe_token"),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
