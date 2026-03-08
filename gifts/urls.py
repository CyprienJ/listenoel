from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.welcome, name="welcome"),
    path("register/", views.register, name="register"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="welcome"), name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("list/<int:user_id>/", views.view_list, name="view_list"),
    path("group/create/", views.create_group, name="create_group"),
    path("group/join/", views.join_group, name="join_group"),
    path("group/<int:group_id>/", views.group_detail, name="group_detail"),
    path("group/<int:group_id>/edit/", views.edit_group, name="edit_group"),
    path("group/<int:group_id>/regenerate-token/", views.regenerate_group_token, name="regenerate_group_token"),
    path("add-gift/<int:owner_id>/", views.add_gift, name="add_gift"),
    path("edit-gift/<int:gift_id>/", views.edit_gift, name="edit_gift"),
    path("delete-gift/<int:gift_id>/", views.delete_gift, name="delete_gift"),
    path("group/<int:group_id>/leave/", views.leave_group, name="leave_group"),
    path("change-password/", views.change_password, name="change_password"),
    path("profile/", views.profile, name="profile"),
    path("profile/delete/", views.delete_account, name="delete_account"),
    path("verify-email/", views.verify_email_sent, name="verify_email_sent"),
    path("verify-email/confirm/<uidb64>/<token>/", views.verify_email_confirm, name="verify_email_confirm"),
    path("verify-email/resend/", views.resend_verification, name="resend_verification"),
    path("subscribe/<int:user_id>/", views.toggle_subscription, name="toggle_subscription"),
    path("unsubscribe/<uidb64>/<token>/", views.unsubscribe_token, name="unsubscribe_token"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="emails/password_reset_email.txt",
            html_email_template_name="emails/password_reset_email.html",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(template_name="registration/password_reset_done.html"),
        name="password_reset_done",
    ),
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(template_name="registration/password_reset_confirm.html"),
        name="password_reset_confirm",
    ),
    path(
        "password-reset-complete/",
        auth_views.PasswordResetCompleteView.as_view(template_name="registration/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    path("gift/<int:gift_id>/reserve/", views.reserve_gift, name="reserve_gift"),
    path("gift/<int:gift_id>/modify_reservation/", views.modify_reservation, name="modify_reservation"),
    path("gift/<int:gift_id>/delete_reservation/", views.delete_reservation, name="delete_reservation"),
    path("gift/<int:gift_id>/edit-price/", views.edit_gift_price, name="edit_gift_price"),
]
