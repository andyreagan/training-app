from django.urls import include, path

from . import activity_views, views

urlpatterns = [
    path("", views.integrations_home, name="integrations_home"),
    path("strava/", include("apps.integrations.strava.urls")),
    path("activity/<int:pk>/", activity_views.activity_detail, name="activity_detail"),
    path(
        "activity/<int:pk>/api/power/", activity_views.activity_power_api, name="activity_power_api"
    ),
    path("activity/<int:pk>/rate/", activity_views.rate_effort, name="rate_effort"),
]
