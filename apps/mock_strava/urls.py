"""
URL routes for the mock Strava server.

These mirror the real Strava URL structure:
    /oauth/authorize
    /oauth/token
    /api/v3/athlete
    /api/v3/athlete/activities
    /api/v3/activities/<id>
"""

from django.urls import path

from . import views

urlpatterns = [
    # OAuth
    path("oauth/authorize", views.authorize, name="mock_strava_authorize"),
    path("oauth/token", views.token, name="mock_strava_token"),
    # API v3
    path("api/v3/athlete", views.api_athlete, name="mock_strava_athlete"),
    path(
        "api/v3/athlete/activities",
        views.api_athlete_activities,
        name="mock_strava_activities",
    ),
    path(
        "api/v3/activities/<int:activity_id>",
        views.api_activity_detail,
        name="mock_strava_activity_detail",
    ),
    path(
        "api/v3/activities/<int:activity_id>/streams",
        views.api_activity_streams,
        name="mock_strava_activity_streams",
    ),
]
