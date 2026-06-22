"""
Tests for activity detail page, effort rating, and power API.
"""

import datetime
import json

import pytest
from django.urls import reverse

from apps.integrations.models import Activity, DataSource

# ── Helpers ────────────────────────────────────────────────────────────────────


def _create_activity(user, name="Test Ride", tss=80, power_data=None, perceived_effort=None):
    return Activity.objects.create(
        user=user,
        source=DataSource.STRAVA,
        external_id=f"act-{name}-{id(name)}",
        name=name,
        sport_type="Ride",
        start_datetime=datetime.datetime(2026, 3, 10, 10, 0, tzinfo=datetime.UTC),
        duration_seconds=3600,
        average_watts=200,
        normalized_power=210,
        tss=tss,
        intensity_factor=0.84,
        power_data=power_data,
        perceived_effort=perceived_effort,
    )


def _make_power_data(duration_seconds=3600, base_watts=200):
    """Generate synthetic power data."""
    import random

    random.seed(42)
    watts = [max(0, base_watts + random.randint(-20, 20)) for _ in range(duration_seconds)]
    return {"time": list(range(duration_seconds)), "watts": watts}


# ── Activity detail page ───────────────────────────────────────────────────────


@pytest.mark.django_db
class TestActivityDetail:
    def test_requires_login(self, client, user):
        activity = _create_activity(user)
        response = client.get(reverse("activity_detail", args=[activity.pk]))
        assert response.status_code in (301, 302)

    def test_loads_for_owner(self, auth_client, user):
        activity = _create_activity(user)
        response = auth_client.get(reverse("activity_detail", args=[activity.pk]))
        assert response.status_code == 200
        assert b"Test Ride" in response.content

    def test_404_for_other_user(self, auth_client, db):
        from django.contrib.auth import get_user_model

        other = get_user_model().objects.create_user(username="other", password="pass")
        activity = _create_activity(other)
        response = auth_client.get(reverse("activity_detail", args=[activity.pk]))
        assert response.status_code == 404

    def test_shows_stats(self, auth_client, user):
        activity = _create_activity(user)
        response = auth_client.get(reverse("activity_detail", args=[activity.pk]))
        content = response.content.decode()
        assert "210" in content  # NP
        assert "80" in content  # TSS

    def test_shows_no_power_message_without_stream(self, auth_client, user):
        activity = _create_activity(user, power_data=None)
        response = auth_client.get(reverse("activity_detail", args=[activity.pk]))
        content = response.content.decode()
        assert "No second-by-second power data" in content

    def test_shows_chart_with_power_data(self, auth_client, user):
        power = _make_power_data()
        activity = _create_activity(user, power_data=power)
        response = auth_client.get(reverse("activity_detail", args=[activity.pk]))
        content = response.content.decode()
        assert "power-time-chart" in content


# ── Effort rating ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestEffortRating:
    def test_rate_effort(self, auth_client, user):
        activity = _create_activity(user)
        response = auth_client.post(
            reverse("rate_effort", args=[activity.pk]),
            {"perceived_effort": "7"},
        )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["perceived_effort"] == 7
        assert data["effort_label"] == "Very hard"

        activity.refresh_from_db()
        assert activity.perceived_effort == 7
        assert activity.effort_source == "manual"

    def test_rate_effort_out_of_range(self, auth_client, user):
        activity = _create_activity(user)
        response = auth_client.post(
            reverse("rate_effort", args=[activity.pk]),
            {"perceived_effort": "11"},
        )
        assert response.status_code == 400

    def test_rate_effort_zero(self, auth_client, user):
        activity = _create_activity(user)
        response = auth_client.post(
            reverse("rate_effort", args=[activity.pk]),
            {"perceived_effort": "0"},
        )
        assert response.status_code == 400

    def test_manual_rating_not_overwritten_by_strava(self, user):
        """Once user manually rates, Strava sync should not overwrite."""
        from apps.integrations.strava.views import _upsert_activity

        activity = _create_activity(user, perceived_effort=8)
        activity.effort_source = "manual"
        activity.save()

        # Simulate a re-sync with Strava RPE of 5
        raw = {
            "id": activity.external_id,
            "name": "Re-synced Ride",
            "start_date": "2026-03-10T10:00:00Z",
            "moving_time": 3600,
            "distance": 40000,
            "total_elevation_gain": 500,
            "average_watts": 200,
            "weighted_average_watts": 210,
            "sport_type": "Ride",
            "type": "Ride",
            "perceived_exertion": 5,
        }
        _upsert_activity(user, raw)

        activity.refresh_from_db()
        assert activity.perceived_effort == 8  # should NOT be overwritten
        assert activity.effort_source == "manual"

    def test_strava_rpe_synced_when_no_manual(self, user):
        """Strava perceived_exertion should be stored if no manual rating exists."""
        from apps.integrations.strava.views import _upsert_activity

        raw = {
            "id": "strava-rpe-test",
            "name": "RPE Test Ride",
            "start_date": "2026-03-10T10:00:00Z",
            "moving_time": 3600,
            "distance": 40000,
            "total_elevation_gain": 500,
            "average_watts": 200,
            "weighted_average_watts": 210,
            "sport_type": "Ride",
            "type": "Ride",
            "perceived_exertion": 7,
        }
        _upsert_activity(user, raw)

        activity = Activity.objects.get(external_id="strava-rpe-test")
        assert activity.perceived_effort == 7
        assert activity.effort_source == "strava"

    def test_404_for_other_users_activity(self, auth_client, db):
        from django.contrib.auth import get_user_model

        other = get_user_model().objects.create_user(username="other2", password="pass")
        activity = _create_activity(other)
        response = auth_client.post(
            reverse("rate_effort", args=[activity.pk]),
            {"perceived_effort": "5"},
        )
        assert response.status_code == 404


# ── Power API ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestPowerAPI:
    def test_404_without_power_data(self, auth_client, user):
        activity = _create_activity(user, power_data=None)
        response = auth_client.get(reverse("activity_power_api", args=[activity.pk]))
        assert response.status_code == 404

    def test_returns_power_data(self, auth_client, user):
        power = _make_power_data()
        activity = _create_activity(user, power_data=power)
        response = auth_client.get(reverse("activity_power_api", args=[activity.pk]))
        assert response.status_code == 200
        data = json.loads(response.content)

        assert "time" in data
        assert "watts_raw" in data
        assert "watts_smoothed" in data
        assert "power_curve" in data
        assert len(data["watts_raw"]) == 3600
        assert len(data["watts_smoothed"]) == 3600

    def test_power_curve_shape(self, auth_client, user):
        power = _make_power_data()
        activity = _create_activity(user, power_data=power)
        response = auth_client.get(reverse("activity_power_api", args=[activity.pk]))
        data = json.loads(response.content)

        curve = data["power_curve"]
        assert len(curve) > 0
        # Should be sorted by duration
        durations = [p["duration"] for p in curve]
        assert durations == sorted(durations)
        # Each point has watts
        assert all("watts" in p for p in curve)

    def test_ftp_estimate_for_long_ride(self, auth_client, user):
        # 1-hour ride at 250W → FTP ≈ 95% of 250 = 237 (or close)
        power = _make_power_data(duration_seconds=3600, base_watts=250)
        activity = _create_activity(user, power_data=power)
        response = auth_client.get(reverse("activity_power_api", args=[activity.pk]))
        data = json.loads(response.content)

        est = data["ftp_estimate"]
        assert est is not None
        assert est["ftp"] > 200
        assert est["method"] in ("20min_95pct", "60min_best")

    def test_no_ftp_estimate_for_short_ride(self, auth_client, user):
        power = _make_power_data(duration_seconds=600)  # 10 min
        activity = _create_activity(user, power_data=power)
        response = auth_client.get(reverse("activity_power_api", args=[activity.pk]))
        data = json.loads(response.content)
        assert data["ftp_estimate"] is None


# ── Intended effort on WorkoutBlock ────────────────────────────────────────────


@pytest.mark.django_db
class TestIntendedEffort:
    def test_recovery_low_effort(self, seeded_plans):
        from apps.plans.models import WorkoutBlock

        recovery = WorkoutBlock.objects.filter(category="recovery").first()
        assert recovery.intended_effort == 2

    def test_vo2max_high_effort(self, seeded_plans):
        from apps.plans.models import WorkoutBlock

        vo2 = WorkoutBlock.objects.filter(category="vo2max").first()
        assert vo2.intended_effort == 9

    def test_threshold_effort(self, seeded_plans):
        from apps.plans.models import WorkoutBlock

        threshold = WorkoutBlock.objects.filter(category="threshold").first()
        assert threshold.intended_effort == 8

    def test_endurance_effort(self, seeded_plans):
        from apps.plans.models import WorkoutBlock

        endurance = WorkoutBlock.objects.filter(category="endurance").first()
        assert endurance.intended_effort == 4
