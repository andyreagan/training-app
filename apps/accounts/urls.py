from django.urls import path

from . import views

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("demo/", views.demo_login_view, name="demo_login"),
    path("profile/", views.profile_view, name="profile"),
    path("ftp/", views.ftp_history_view, name="ftp_history"),
    path("ftp/<int:pk>/edit/", views.ftp_history_edit, name="ftp_history_edit"),
    path("ftp/<int:pk>/delete/", views.ftp_history_delete, name="ftp_history_delete"),
]
