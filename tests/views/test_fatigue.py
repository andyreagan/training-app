"""
View tests for the fatigue monitor.

Creates Activities and ScheduledWorkouts, hits the JSON endpoints,
and verifies the response shape and data correctness.
"""

import datetime
import json

import pytest
from django.urls import reverse

from apps.integrations.models import Activity, DataSource
from apps.plans.models import WorkoutBlock
from apps.scheduler.models import ScheduledWorkout

# ── Helpers ────────────────────────────────────────────────────────────────────


def _create_activity(user, date, tss, name="Ride"):
    return Activity.objects.create(
        user=user,
        source=DataSource.STRAVA,
        external_id=f"act-{date}-{tss}",
        name=name,
        sport_type="Ride",
        start_datetime=datetime.datetime.combine(date, datetime.time(10, 0), tzinfo=datetime.UTC),
        duration_seconds=3600,
        tss=tss,
    )


def _get_or_create_workout(category="endurance", score=3.0):
    return WorkoutBlock.objects.get_or_create(
        category=category,
        progression_score=score,
        defaults={"name": f"Test {category} {score}", "slug": f"test-{category}-{score}"},
    )[0]


# ── Dashboard page ─────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestFatigueDashboard:
    def test_requires_login(self, client):
        response = client.get(reverse("fatigue_dashboard"))
        assert response.status_code in (301, 302)
        assert "login" in response["Location"]

    def test_page_loads(self, auth_client):
        response = auth_client.get(reverse("fatigue_dashboard"))
        assert response.status_code == 200
        assert b"Fatigue Monitor" in response.content


# ── Data API ───────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestFatigueDataAPI:
    def test_requires_login(self, client):
        response = client.get(reverse("fatigue_data_api"))
        assert response.status_code in (301, 302)

    def test_empty_returns_empty_array(self, auth_client):
        response = auth_client.get(reverse("fatigue_data_api"))
        assert response.status_code == 200
        data = json.loads(response.content)
        assert isinstance(data, list)
        assert len(data) == 0

    def test_returns_metrics_for_activities(self, auth_client, user):
        today = datetime.date.today()
        _create_activity(user, today - datetime.timedelta(days=5), tss=80)
        _create_activity(user, today - datetime.timedelta(days=3), tss=100)
        _create_activity(user, today - datetime.timedelta(days=1), tss=60)

        response = auth_client.get(
            reverse("fatigue_data_api"), {"days_back": 10, "days_forward": 0}
        )
        data = json.loads(response.content)

        assert len(data) > 0
        # Each entry should have the expected keys
        for entry in data:
            assert set(entry.keys()) == {
                "date",
                "tss",
                "ctl",
                "atl",
                "tsb",
                "source",
                "zone",
                "color",
            }

        # The days with activities should have non-zero TSS
        dates_with_tss = {e["date"] for e in data if e["tss"] > 0}
        assert len(dates_with_tss) == 3

    def test_includes_planned_workouts(self, auth_client, user):
        today = datetime.date.today()
        workout = _get_or_create_workout()
        ScheduledWorkout.objects.create(
            user=user,
            workout=workout,
            date=today + datetime.timedelta(days=3),
        )

        response = auth_client.get(
            reverse("fatigue_data_api"),
            {"days_back": 5, "days_forward": 10},
        )
        data = json.loads(response.content)

        planned = [e for e in data if e["source"] == "planned"]
        assert len(planned) >= 1
        assert planned[0]["tss"] > 0

    def test_completed_workouts_use_activity_tss(self, auth_client, user):
        """A completed ScheduledWorkout with a linked Activity should use actual TSS."""
        today = datetime.date.today()
        workout = _get_or_create_workout()
        activity = _create_activity(user, today - datetime.timedelta(days=1), tss=95, name="Linked")
        ScheduledWorkout.objects.create(
            user=user,
            workout=workout,
            date=today - datetime.timedelta(days=1),
            completed=True,
            activity=activity,
        )

        response = auth_client.get(
            reverse("fatigue_data_api"),
            {"days_back": 5, "days_forward": 0},
        )
        data = json.loads(response.content)

        yesterday = (today - datetime.timedelta(days=1)).isoformat()
        day_entry = next((e for e in data if e["date"] == yesterday), None)
        assert day_entry is not None
        assert day_entry["tss"] == 95.0
        assert day_entry["source"] == "actual"

    def test_multiple_activities_same_day_sum_tss(self, auth_client, user):
        today = datetime.date.today()
        _create_activity(user, today - datetime.timedelta(days=2), tss=50, name="AM Ride")
        # Need a different external_id
        Activity.objects.create(
            user=user,
            source=DataSource.STRAVA,
            external_id=f"act-pm-{today}",
            name="PM Ride",
            sport_type="Ride",
            start_datetime=datetime.datetime.combine(
                today - datetime.timedelta(days=2), datetime.time(17, 0), tzinfo=datetime.UTC
            ),
            duration_seconds=3600,
            tss=30,
        )

        response = auth_client.get(
            reverse("fatigue_data_api"),
            {"days_back": 5, "days_forward": 0},
        )
        data = json.loads(response.content)

        target_date = (today - datetime.timedelta(days=2)).isoformat()
        day_entry = next((e for e in data if e["date"] == target_date), None)
        assert day_entry is not None
        assert day_entry["tss"] == 80.0  # 50 + 30

    def test_days_back_and_forward_params(self, auth_client, user):
        today = datetime.date.today()
        _create_activity(user, today, tss=70)

        response = auth_client.get(
            reverse("fatigue_data_api"),
            {"days_back": 3, "days_forward": 5},
        )
        data = json.loads(response.content)

        dates = [e["date"] for e in data]
        earliest = datetime.date.fromisoformat(dates[0])
        latest = datetime.date.fromisoformat(dates[-1])

        assert earliest >= today - datetime.timedelta(days=3)
        assert latest <= today + datetime.timedelta(days=5)

    def test_tsb_zones_in_response(self, auth_client, user):
        today = datetime.date.today()
        _create_activity(user, today, tss=50)

        response = auth_client.get(
            reverse("fatigue_data_api"),
            {"days_back": 1, "days_forward": 0},
        )
        data = json.loads(response.content)

        for entry in data:
            assert entry["zone"] in ("fresh", "neutral", "tired", "danger")
            assert entry["color"].startswith("#")


# ── Calendar TSB API ───────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestCalendarTSBAPI:
    def test_requires_login(self, client):
        response = client.get(reverse("calendar_tsb_api"))
        assert response.status_code in (301, 302)

    def test_returns_dict_keyed_by_date(self, auth_client, user):
        today = datetime.date.today()
        _create_activity(user, today - datetime.timedelta(days=1), tss=80)

        response = auth_client.get(
            reverse("calendar_tsb_api"),
            {
                "start": (today - datetime.timedelta(days=5)).isoformat(),
                "end": today.isoformat(),
            },
        )
        data = json.loads(response.content)
        assert isinstance(data, dict)

        for date_str, info in data.items():
            datetime.date.fromisoformat(date_str)  # should not raise
            assert "tsb" in info
            assert "zone" in info
            assert "color" in info

    def test_empty_history_returns_empty(self, auth_client):
        response = auth_client.get(
            reverse("calendar_tsb_api"),
            {"start": "2026-03-01", "end": "2026-03-31"},
        )
        data = json.loads(response.content)
        assert data == {}
