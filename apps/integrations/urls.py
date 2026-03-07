from django.urls import path, include
from . import views

urlpatterns = [
    path("", views.integrations_home, name="integrations_home"),
    path("strava/", include("apps.integrations.strava.urls")),
]
