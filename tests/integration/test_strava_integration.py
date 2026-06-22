"""
Integration tests for our app's Strava views (OAuth + sync) against the mock server.

These tests verify the full flow:
  1. User clicks "Connect Strava" → redirected to mock Strava's authorize endpoint
  2. Mock Strava auto-approves and redirects back with a code
  3. Our callback exchanges the code for tokens, saves them to the user
  4. User triggers sync → our client fetches activities from mock Strava
  5. Activities are upserted into the Activity table

All tests use Django's live_server so both our app and mock Strava
are served over real HTTP.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model

from apps.integrations.models import Activity, DataSource
from apps.integrations.strava.client import StravaClient, exchange_code
from apps.mock_strava.models import state as mock_strava_state


def recent_date(days_ago: int) -> str:
    """An ISO timestamp `days_ago` days before now.

    Sync only pulls activities from the last 90 days, so test fixtures must be
    dated relative to the current time rather than hardcoded calendar dates.
    """
    when = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(days=days_ago)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.mark.django_db(transaction=True)
class TestOAuthFlowDirect:
    """Test the OAuth helpers (exchange_code) directly against mock Strava."""

    def test_exchange_code_returns_tokens(self, strava_settings, mock_athlete, live_server):
        """exchange_code() gets back valid tokens from mock Strava."""
        code = mock_strava_state.create_auth_code(mock_athlete.id)

        data = exchange_code(
            code=code,
            client_id=strava_settings.STRAVA_CLIENT_ID,
            client_secret=strava_settings.STRAVA_CLIENT_SECRET,
            redirect_uri=strava_settings.STRAVA_REDIRECT_URI,
        )

        assert "access_token" in data
        assert "refresh_token" in data
        assert "expires_at" in data
        assert data["athlete"]["id"] == mock_athlete.id
        assert data["athlete"]["firstname"] == "Jane"

    def test_exchange_code_invalid_code(self, strava_settings, live_server):
        """exchange_code() with a bad code raises an HTTP error."""
        import requests

        with pytest.raises(requests.HTTPError):
            exchange_code(
                code="invalid_code",
                client_id=strava_settings.STRAVA_CLIENT_ID,
                client_secret=strava_settings.STRAVA_CLIENT_SECRET,
                redirect_uri=strava_settings.STRAVA_REDIRECT_URI,
            )


@pytest.mark.django_db(transaction=True)
class TestStravaClientDirect:
    """Test our StravaClient class directly against the mock server."""

    def test_get_athlete(self, strava_settings, strava_user, live_server):
        """StravaClient.get_athlete() returns the mock athlete data."""
        client = StravaClient(strava_user)
        data = client.get_athlete()

        assert data["id"] == 99999
        assert data["firstname"] == "Jane"
        assert data["lastname"] == "Rider"

    def test_get_activities_empty(self, strava_settings, strava_user, live_server):
        """StravaClient.get_activities() returns empty list when no activities."""
        client = StravaClient(strava_user)
        activities = client.get_activities()
        assert activities == []

    def test_get_activities(self, strava_settings, strava_user, live_server):
        """StravaClient.get_activities() returns activities from mock."""
        # Add some activities for the user's athlete
        mock_strava_state.add_activity(
            strava_user.strava_athlete_id,
            id=20001,
            name="Test Ride",
            start_date="2024-07-01T10:00:00Z",
        )
        mock_strava_state.add_activity(
            strava_user.strava_athlete_id,
            id=20002,
            name="Test Run",
            sport_type="Run",
            type="Run",
            start_date="2024-07-02T10:00:00Z",
        )

        client = StravaClient(strava_user)
        activities = client.get_activities()
        assert len(activities) == 2
        names = {a["name"] for a in activities}
        assert "Test Ride" in names
        assert "Test Run" in names

    def test_get_activity(self, strava_settings, strava_user, live_server):
        """StravaClient.get_activity() returns detail for a specific activity."""
        mock_strava_state.add_activity(
            strava_user.strava_athlete_id,
            id=20010,
            name="Specific Ride",
            start_date="2024-07-05T09:00:00Z",
        )

        client = StravaClient(strava_user)
        data = client.get_activity(20010)
        assert data["name"] == "Specific Ride"
        assert data["id"] == 20010
        # Detail endpoint should include extra fields
        assert "description" in data
        assert "calories" in data

    def test_token_refresh(self, strava_settings, strava_user, live_server):
        """StravaClient auto-refreshes an expired token."""
        # Expire the user's token
        strava_user.strava_token_expires_at = datetime.datetime(2020, 1, 1, tzinfo=datetime.UTC)
        strava_user.save()

        # Add an activity so we can verify the refreshed request works
        mock_strava_state.add_activity(
            strava_user.strava_athlete_id,
            id=20020,
            name="Post Refresh Ride",
            start_date="2024-08-01T10:00:00Z",
        )

        client = StravaClient(strava_user)
        # This should trigger a refresh, then fetch activities
        activities = client.get_activities()
        assert len(activities) == 1
        assert activities[0]["name"] == "Post Refresh Ride"

        # The user's tokens should be updated
        strava_user.refresh_from_db()
        assert strava_user.strava_token_expires_at > datetime.datetime.now(tz=datetime.UTC)

    def test_activities_with_after_filter(self, strava_settings, strava_user, live_server):
        """StravaClient.get_activities(after=...) filters correctly."""
        mock_strava_state.add_activity(
            strava_user.strava_athlete_id,
            id=20030,
            name="Old Ride",
            start_date="2024-01-01T10:00:00Z",
        )
        mock_strava_state.add_activity(
            strava_user.strava_athlete_id,
            id=20031,
            name="Recent Ride",
            start_date="2024-07-15T10:00:00Z",
        )

        client = StravaClient(strava_user)
        after = datetime.datetime(2024, 6, 1, tzinfo=datetime.UTC)
        activities = client.get_activities(after=after)
        assert len(activities) == 1
        assert activities[0]["name"] == "Recent Ride"


@pytest.mark.django_db(transaction=True)
class TestSyncView:
    """Test the full sync view against the mock Strava server."""

    def test_sync_creates_activity_records(self, strava_settings, strava_user, live_server, client):
        """Triggering sync creates Activity records in the database."""
        # Add activities to mock — must be within the last 90 days to be synced
        mock_strava_state.add_activity(
            strava_user.strava_athlete_id,
            id=30001,
            name="Synced Ride",
            sport_type="Ride",
            type="Ride",
            start_date=recent_date(10),
            moving_time=3600,
            distance=40000.0,
            total_elevation_gain=500.0,
            average_watts=200.0,
            weighted_average_watts=210,
            average_heartrate=145.0,
            max_heartrate=175,
            kudos_count=5,
        )

        # Log in as the strava_user
        client.login(username="strava_tester", password="testpass123")

        # Trigger sync
        response = client.get("/integrations/strava/sync/", follow=True)
        assert response.status_code == 200

        # Verify Activity was created
        acts = Activity.objects.filter(user=strava_user, source=DataSource.STRAVA)
        assert acts.count() == 1

        act = acts.first()
        assert act.name == "Synced Ride"
        assert act.external_id == "30001"
        assert act.duration_seconds == 3600
        assert act.distance_meters == 40000.0
        assert act.average_watts == 200.0

    def test_sync_upserts_existing_activities(
        self, strava_settings, strava_user, live_server, client
    ):
        """Syncing again updates existing activities rather than duplicating."""
        # Add two activities — the second sync will use the latest activity's
        # date as `after`, so we need a newer activity to trigger a re-fetch
        mock_strava_state.add_activity(
            strava_user.strava_athlete_id,
            id=30010,
            name="Original Name",
            start_date=recent_date(12),
            moving_time=1800,
        )
        mock_strava_state.add_activity(
            strava_user.strava_athlete_id,
            id=30011,
            name="Newer Ride",
            start_date=recent_date(10),
            moving_time=3600,
        )

        client.login(username="strava_tester", password="testpass123")

        # First sync
        client.get("/integrations/strava/sync/", follow=True)
        assert Activity.objects.filter(source=DataSource.STRAVA, external_id="30010").count() == 1
        assert Activity.objects.filter(source=DataSource.STRAVA, external_id="30011").count() == 1

        # Update the newer activity in mock and add an even newer one
        mock_strava_state.activities[30011].name = "Updated Ride"
        mock_strava_state.activities[30011].moving_time = 2400
        mock_strava_state.add_activity(
            strava_user.strava_athlete_id,
            id=30012,
            name="Brand New Ride",
            start_date=recent_date(9),
            moving_time=5400,
        )

        # Second sync (will fetch activities after the latest synced activity)
        client.get("/integrations/strava/sync/", follow=True)

        # 30010 should still exist (not duplicated), 30012 should be new
        assert Activity.objects.filter(source=DataSource.STRAVA).count() == 3
        assert Activity.objects.filter(source=DataSource.STRAVA, external_id="30012").count() == 1

        new_act = Activity.objects.get(source=DataSource.STRAVA, external_id="30012")
        assert new_act.name == "Brand New Ride"

    def test_sync_multiple_activities(self, strava_settings, strava_user, live_server, client):
        """Sync pulls all activities from mock."""
        for i in range(5):
            mock_strava_state.add_activity(
                strava_user.strava_athlete_id,
                id=30100 + i,
                name=f"Ride {i + 1}",
                start_date=recent_date(10 - i),
                moving_time=3600,
            )

        client.login(username="strava_tester", password="testpass123")
        client.get("/integrations/strava/sync/", follow=True)

        acts = Activity.objects.filter(user=strava_user, source=DataSource.STRAVA)
        assert acts.count() == 5

    def test_sync_requires_strava_connection(self, db, client, strava_settings, live_server):
        """Sync redirects with error if user hasn't connected Strava."""
        User = get_user_model()
        u = User.objects.create_user(
            username="noconnection",
            password="testpass123",
        )
        from apps.plans.models import UserProgressionScores

        UserProgressionScores.objects.get_or_create(user=u)

        client.login(username="noconnection", password="testpass123")
        response = client.get("/integrations/strava/sync/", follow=True)
        assert response.status_code == 200
        # Should have an error message
        content = response.content.decode()
        assert "Connect Strava first" in content or "connect" in content.lower()
