from django.urls import path
from . import views

urlpatterns = [
    path('', views.choose_family, name='choose_family'),
    path('family/<int:family_id>/', views.choose_person_in_family, name='choose_person_in_family'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('list/<int:person_id>/', views.view_list, name='view_list'),
    path('reserve/<int:gift_id>/', views.reserve_gift, name='reserve_gift'),
    path('unreserve/<int:gift_id>/', views.unreserve_gift, name='unreserve_gift'),
    path('add-gift/', views.add_gift, name='add_gift'),
    path('edit-gift/<int:gift_id>/', views.edit_gift, name='edit_gift'),
    path('delete-gift/<int:gift_id>/', views.delete_gift, name='delete_gift'),
    path('logout/', views.logout, name='logout'),
    path("change-password/", views.change_password_form, name="change_password_form"),
    path("change-password/submit/", views.change_password, name="change_password"),

]
