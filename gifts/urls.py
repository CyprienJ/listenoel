from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import account, events, groups, views
from .feeds import SubscriptionFeed

urlpatterns = [
    # Default
    path("", views.welcome, name="welcome"),
    path("privacy/", views.privacy, name="privacy"),
    path("dashboard/", views.dashboard, name="dashboard"),
    # Auth
    path("demo/", account.demo_login, name="demo_login"),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="welcome"), name="logout"),
    # Settings
    path("register/", account.register, name="register"),
    path(
        "account/change_password/",
        account.DemoProtectedPasswordChangeView.as_view(
            template_name="registration/change_password.html", success_url="/account/"
        ),
        name="account/change_password/",
    ),
    path("account/", account.account, name="account"),
    path("account/photo/", account.photo_upload, name="photo_upload_profile"),
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
    path("group/<int:group_id>/photo/", groups.group_photo_upload, name="photo_upload_group"),
    path("group/<int:group_id>/regenerate-token/", groups.regenerate_group_token, name="regenerate_group_token"),
    path("group/<int:group_id>/leave/", groups.leave_group, name="leave_group"),
    path("group/<int:group_id>/managed/add/", groups.add_managed_member, name="add_managed_member"),
    path("group/<int:group_id>/managed/<int:member_id>/", groups.view_managed_list, name="view_managed_list"),
    path(
        "group/<int:group_id>/managed/<int:member_id>/rename/",
        groups.rename_managed_member,
        name="rename_managed_member",
    ),
    path(
        "group/<int:group_id>/managed/<int:member_id>/delete/",
        groups.delete_managed_member,
        name="delete_managed_member",
    ),
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
    path("balance/<int:group_id>/", views.balance_view, name="balance_group"),
    path("group/<int:group_id>/add-settlement/", views.add_settlement, name="add_settlement"),
    # Event lists
    path("event/create/", events.create_event_list, name="create_event_list"),
    path("event/<str:token>/", events.event_detail, name="event_detail"),
    path("event/<str:token>/guest/", events.set_guest_name, name="event_set_guest"),
    path("event/<str:token>/gift/add/", events.add_event_gift, name="add_event_gift"),
    path("event/<str:token>/gift/<int:gift_id>/edit/", events.edit_event_gift, name="edit_event_gift"),
    path("event/<str:token>/gift/<int:gift_id>/delete/", events.delete_event_gift, name="delete_event_gift"),
    path(
        "event/<str:token>/gift/<int:gift_id>/hide/",
        events.toggle_event_gift_hidden,
        name="toggle_event_gift_hidden",
    ),
    path("event/<str:token>/gift/<int:gift_id>/reserve/", events.reserve_event_gift, name="reserve_event_gift"),
    path("event/<str:token>/gift/<int:gift_id>/transfer/", events.transfer_event_gift, name="transfer_event_gift"),
    path("event/<str:token>/edit-info/", events.edit_event_info, name="edit_event_info"),
    path(
        "event/<str:token>/secret-santa/exclusion/add/",
        events.add_secret_santa_exclusion,
        name="add_secret_santa_exclusion",
    ),
    path(
        "event/<str:token>/secret-santa/guest/add/",
        events.add_secret_santa_guest_participant,
        name="add_secret_santa_guest_participant",
    ),
    path(
        "event/<str:token>/secret-santa/guest/<int:guest_id>/delete/",
        events.delete_secret_santa_guest_participant,
        name="delete_secret_santa_guest_participant",
    ),
    path(
        "event/<str:token>/secret-santa/exclusion/<int:exclusion_id>/delete/",
        events.delete_secret_santa_exclusion,
        name="delete_secret_santa_exclusion",
    ),
    path("event/<str:token>/secret-santa/draw/", events.draw_secret_santa, name="draw_secret_santa"),
    path("event/<str:token>/leave/", events.leave_event_list, name="leave_event_list"),
    path("event/<str:token>/delete/", events.delete_event_list, name="delete_event_list"),
    path("event/<str:token>/regenerate/", events.regenerate_event_token, name="regenerate_event_token"),
    path("event/<str:token>/photo/", events.event_photo_upload, name="event_photo_upload"),
    # Notification
    path("notifications/", views.notification_center, name="notification_center"),
    path("subscribe/<int:user_id>/", views.toggle_subscription, name="toggle_subscription"),
    path("feeds/subscriptions/<uuid:feed_token>/", SubscriptionFeed(), name="subscription_feed"),
    path(
        "unsubscribe/<int:owner_id>/<uidb64>/<token>/",
        views.unsubscribe_token,
        name="unsubscribe_token",
    ),
]


if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
