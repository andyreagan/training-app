"""
Validate mock Strava API against the stravalib library.

These tests prove that our mock server is complete enough for stravalib's
Client to work against — the same library many real Strava integrations use.

Each test uses Django's live_server fixture so the mock Strava app is
served over HTTP, and stravalib talks to it via real HTTP requests.
"""

import os

import pytest

from apps.mock_strava.models import state as mock_strava_state

# stravalib checks for env vars on import — silence warnings
os.environ.setdefault("SILENCE_TOKEN_WARNINGS", "true")

from stravalib import Client as StravaLibClient  # noqa: E402


@pytest.mark.django_db(transaction=True)
class TestStravaLibOAuth:
    """Test that stravalib's OAuth flow works against our mock."""

    def test_authorization_url_generation(self, mock_strava_url):
        """stravalib can generate a valid authorization URL."""
        client = StravaLibClient()
        # Override the server to point at our mock
        client.protocol.server = mock_strava_url.replace("http://", "")
        # stravalib always generates https URLs, so we test the structure
        url = client.authorization_url(
            client_id=12345,
            redirect_uri="http://localhost/callback",
            scope=["activity:read_all"],
        )
        assert "client_id=12345" in url
        assert "redirect_uri=" in url
        assert "activity%3Aread_all" in url

    def test_exchange_code_for_token(self, mock_strava_url, mock_athlete):
        """stravalib can exchange an auth code for tokens via our mock."""
        code = mock_strava_state.create_auth_code(mock_athlete.id)

        client = StravaLibClient()
        # Point stravalib at our mock server (http, not https)
        _patch_stravalib_server(client, mock_strava_url)

        token_response = client.exchange_code_for_token(
            client_id=12345,
            client_secret="test_secret",
            code=code,
        )

        assert "access_token" in token_response
        assert "refresh_token" in token_response
        assert "expires_at" in token_response
        assert len(token_response["access_token"]) > 0

    def test_exchange_code_returns_athlete(self, mock_strava_url, mock_athlete):
        """stravalib can retrieve athlete info during code exchange."""
        code = mock_strava_state.create_auth_code(mock_athlete.id)

        client = StravaLibClient()
        _patch_stravalib_server(client, mock_strava_url)

        token_response, athlete = client.exchange_code_for_token(
            client_id=12345,
            client_secret="test_secret",
            code=code,
            return_athlete=True,
        )

        assert athlete is not None
        assert athlete.id == mock_athlete.id
        assert athlete.firstname == "Jane"
        assert athlete.lastname == "Rider"

    def test_refresh_access_token(self, mock_strava_url, mock_athlete):
        """stravalib can refresh an expired token via our mock."""
        access, refresh, expires_at = mock_strava_state.create_tokens(mock_athlete.id)

        client = StravaLibClient(access_token=access)
        _patch_stravalib_server(client, mock_strava_url)

        new_token = client.refresh_access_token(
            client_id=12345,
            client_secret="test_secret",
            refresh_token=refresh,
        )

        assert "access_token" in new_token
        assert "refresh_token" in new_token
        assert new_token["access_token"] != access  # should be a new token


@pytest.mark.django_db(transaction=True)
class TestStravaLibAPI:
    """Test that stravalib's API methods work against our mock endpoints."""

    def test_get_athlete(self, mock_strava_url, mock_athlete):
        """stravalib can fetch the authenticated athlete."""
        access, _, _ = mock_strava_state.create_tokens(mock_athlete.id)

        client = StravaLibClient(access_token=access)
        _patch_stravalib_server(client, mock_strava_url)

        athlete = client.get_athlete()

        assert athlete.id == mock_athlete.id
        assert athlete.firstname == "Jane"
        assert athlete.lastname == "Rider"
        assert athlete.ftp == 280
        assert athlete.weight == 65.0

    def test_get_activities_empty(self, mock_strava_url, mock_athlete):
        """stravalib returns empty iterator when no activities exist."""
        access, _, _ = mock_strava_state.create_tokens(mock_athlete.id)

        client = StravaLibClient(access_token=access)
        _patch_stravalib_server(client, mock_strava_url)

        activities = list(client.get_activities())
        assert activities == []

    def test_get_activities(self, mock_strava_url, mock_athlete_with_activities):
        """stravalib can list activities from our mock."""
        access, _, _ = mock_strava_state.create_tokens(mock_athlete_with_activities.id)

        client = StravaLibClient(access_token=access)
        _patch_stravalib_server(client, mock_strava_url)

        activities = list(client.get_activities())
        assert len(activities) == 3

        # Verify the activities are parsed into stravalib model objects
        names = {a.name for a in activities}
        assert "Morning Ride" in names
        assert "Afternoon Spin" in names
        assert "Weekend Long Ride" in names

    def test_get_activities_with_limit(self, mock_strava_url, mock_athlete_with_activities):
        """stravalib respects limit parameter."""
        access, _, _ = mock_strava_state.create_tokens(mock_athlete_with_activities.id)

        client = StravaLibClient(access_token=access)
        _patch_stravalib_server(client, mock_strava_url)

        activities = list(client.get_activities(limit=2))
        assert len(activities) == 2

    def test_get_activities_with_after(self, mock_strava_url, mock_athlete_with_activities):
        """stravalib can filter activities by after date."""
        import datetime

        access, _, _ = mock_strava_state.create_tokens(mock_athlete_with_activities.id)

        client = StravaLibClient(access_token=access)
        _patch_stravalib_server(client, mock_strava_url)

        # Only activities after June 16 — should get "Afternoon Spin" and "Weekend Long Ride"
        after = datetime.datetime(2024, 6, 16, 0, 0, 0, tzinfo=datetime.UTC)
        activities = list(client.get_activities(after=after))
        assert len(activities) == 2
        names = {a.name for a in activities}
        assert "Morning Ride" not in names

    def test_get_activity_detail(self, mock_strava_url, mock_athlete_with_activities):
        """stravalib can fetch a single activity detail."""
        access, _, _ = mock_strava_state.create_tokens(mock_athlete_with_activities.id)

        client = StravaLibClient(access_token=access)
        _patch_stravalib_server(client, mock_strava_url)

        activity = client.get_activity(10001)
        assert activity.id == 10001
        assert activity.name == "Morning Ride"
        assert activity.sport_type.root == "Ride"
        assert activity.kudos_count == 5
        assert activity.average_watts == 200.0

    def test_get_activity_not_found(self, mock_strava_url, mock_athlete):
        """stravalib raises an error for non-existent activity."""
        from stravalib import exc as stravalib_exc

        access, _, _ = mock_strava_state.create_tokens(mock_athlete.id)

        client = StravaLibClient(access_token=access)
        _patch_stravalib_server(client, mock_strava_url)

        with pytest.raises(stravalib_exc.ObjectNotFound):
            client.get_activity(99999)

    def test_activity_model_fields(self, mock_strava_url, mock_athlete_with_activities):
        """Verify key fields on stravalib activity models are populated."""
        access, _, _ = mock_strava_state.create_tokens(mock_athlete_with_activities.id)

        client = StravaLibClient(access_token=access)
        _patch_stravalib_server(client, mock_strava_url)

        activities = list(client.get_activities())
        ride = next(a for a in activities if a.name == "Morning Ride")

        # These are the fields our app's _upsert_activity() depends on
        assert ride.id == 10001
        assert ride.name == "Morning Ride"
        assert ride.sport_type is not None
        assert ride.start_date is not None
        assert ride.moving_time is not None
        assert ride.distance is not None
        assert ride.total_elevation_gain is not None
        assert ride.average_watts == 200.0
        assert ride.weighted_average_watts == 210
        assert ride.average_heartrate == 145.0
        assert ride.max_heartrate == 175
        assert ride.kudos_count == 5

    def test_unauthorized_request(self, mock_strava_url, mock_athlete):
        """stravalib raises error for invalid token."""
        from stravalib import exc as stravalib_exc

        client = StravaLibClient(access_token="invalid_token_abc")
        _patch_stravalib_server(client, mock_strava_url)

        with pytest.raises(stravalib_exc.AccessUnauthorized):
            client.get_athlete()


# ── Helper ─────────────────────────────────────────────────────────────────────


def _patch_stravalib_server(client: StravaLibClient, mock_url: str):
    """
    Patch a stravalib Client's protocol to talk to our mock server over HTTP.

    stravalib hardcodes ``https://www.strava.com`` — we override both the
    server hostname and the resolve_url method so it uses HTTP instead.
    """
    # e.g. "http://localhost:12345/mock-strava"
    # We need protocol.server to be the authority part and api_base to route correctly.
    # The cleanest approach: override resolve_url to use the mock URL directly.
    proto = client.protocol
    base_url = mock_url.rstrip("/")

    def patched_resolve_url(url):
        if url.startswith("http"):
            # Already absolute — rewrite strava.com to our mock
            return url.replace("https://www.strava.com", base_url)
        # Relative URL like /api/v3/athlete
        return f"{base_url}{proto.api_base}/{url.strip('/')}"

    proto.resolve_url = patched_resolve_url
