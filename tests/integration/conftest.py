"""
Integration test fixtures for the mock Strava server.

These tests run against Django's live_server and verify that:
  1. Our mock Strava API is complete enough for stravalib to work against.
  2. Our app's Strava integration (OAuth flow, sync) works end-to-end.
"""

import os

import pytest
from django.contrib.auth import get_user_model

# Ensure the mock Strava app is available
os.environ.setdefault("SILENCE_TOKEN_WARNINGS", "true")

from apps.mock_strava.models import state as mock_strava_state


@pytest.fixture(autouse=True)
def _reset_mock_strava():
    """Reset mock Strava state before every test."""
    mock_strava_state.reset()
    yield
    mock_strava_state.reset()


@pytest.fixture
def mock_strava_url(live_server):
    """The base URL for the mock Strava server (e.g. http://localhost:12345/mock-strava)."""
    return f"{live_server.url}/mock-strava"


@pytest.fixture
def strava_settings(mock_strava_url, settings):
    """
    Configure Django settings to point at the mock Strava server.
    """
    settings.STRAVA_BASE_URL = mock_strava_url
    settings.STRAVA_CLIENT_ID = "12345"
    settings.STRAVA_CLIENT_SECRET = "test_secret"
    settings.STRAVA_REDIRECT_URI = "http://localhost/integrations/strava/callback/"
    return settings


@pytest.fixture
def mock_athlete():
    """Register a default mock athlete and return it."""
    return mock_strava_state.add_athlete(
        id=99999,
        firstname="Jane",
        lastname="Rider",
        username="janerider",
        ftp=280,
        weight=65.0,
    )


@pytest.fixture
def mock_athlete_with_activities(mock_athlete):
    """Register a mock athlete with several activities."""
    mock_strava_state.add_activity(
        mock_athlete.id,
        id=10001,
        name="Morning Ride",
        sport_type="Ride",
        type="Ride",
        start_date="2024-06-15T10:00:00Z",
        moving_time=3600,
        distance=40000.0,
        total_elevation_gain=500.0,
        average_watts=200.0,
        weighted_average_watts=210,
        average_heartrate=145.0,
        max_heartrate=175,
        kudos_count=5,
    )
    mock_strava_state.add_activity(
        mock_athlete.id,
        id=10002,
        name="Afternoon Spin",
        sport_type="Ride",
        type="Ride",
        start_date="2024-06-16T14:00:00Z",
        moving_time=1800,
        distance=20000.0,
        total_elevation_gain=100.0,
        average_watts=150.0,
        weighted_average_watts=160,
        average_heartrate=130.0,
        max_heartrate=155,
        kudos_count=3,
    )
    mock_strava_state.add_activity(
        mock_athlete.id,
        id=10003,
        name="Weekend Long Ride",
        sport_type="Ride",
        type="Ride",
        start_date="2024-06-17T08:00:00Z",
        moving_time=14400,
        distance=120000.0,
        total_elevation_gain=1500.0,
        average_watts=180.0,
        weighted_average_watts=195,
        average_heartrate=140.0,
        max_heartrate=170,
        kudos_count=12,
    )
    return mock_athlete


@pytest.fixture
def strava_user(db, strava_settings, mock_athlete):
    """
    A Django user with Strava tokens pre-populated from the mock server.
    """
    access, refresh, expires_at = mock_strava_state.create_tokens(mock_athlete.id)

    import datetime

    User = get_user_model()
    u = User.objects.create_user(
        username="strava_tester",
        email="strava@example.com",
        password="testpass123",
    )
    u.record_ftp(250)
    u.strava_athlete_id = mock_athlete.id
    u.strava_access_token = access
    u.strava_refresh_token = refresh
    u.strava_token_expires_at = datetime.datetime.fromtimestamp(expires_at, tz=datetime.UTC)
    u.save()

    # Also create UserProgressionScores if needed
    from apps.plans.models import UserProgressionScores

    UserProgressionScores.objects.get_or_create(user=u)

    return u
