from django.urls import path

from . import views

urlpatterns = [
    path("connect/", views.strava_connect, name="strava_connect"),
    path("callback/", views.strava_callback, name="strava_callback"),
    path("disconnect/", views.strava_disconnect, name="strava_disconnect"),
    path("sync/", views.strava_sync, name="strava_sync"),
]
