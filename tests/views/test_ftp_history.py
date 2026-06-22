"""
Tests for FTP history and weight history — models, views, and the
interaction with Activity TSS calculation.
"""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.accounts.models import FTPHistory, WeightHistory

User = get_user_model()


# ── Model tests ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestFTPHistoryModel:
    def test_record_ftp_creates_entry(self, user):
        user.record_ftp(280, effective_date=datetime.date(2026, 3, 1))
        assert user.ftp == 280
        assert FTPHistory.objects.filter(user=user).count() == 2  # 250 from fixture + 280

    def test_ftp_returns_most_recent(self, user):
        user.record_ftp(260, effective_date=datetime.date(2026, 2, 1))
        user.record_ftp(280, effective_date=datetime.date(2026, 3, 1))
        assert user.ftp == 280

    def test_ftp_respects_date_ordering(self, user):
        """Adding an older entry doesn't change current FTP."""
        user.record_ftp(280, effective_date=datetime.date(2026, 3, 1))
        user.record_ftp(220, effective_date=datetime.date(2025, 1, 1))
        assert user.ftp == 280

    def test_record_ftp_same_date_updates_existing(self, user):
        user.record_ftp(260, effective_date=datetime.date(2026, 3, 1))
        user.record_ftp(270, effective_date=datetime.date(2026, 3, 1))
        assert (
            FTPHistory.objects.filter(user=user, effective_date=datetime.date(2026, 3, 1)).count()
            == 1
        )
        entry = FTPHistory.objects.get(user=user, effective_date=datetime.date(2026, 3, 1))
        assert entry.ftp == 270

    def test_record_ftp_with_source(self, user):
        user.record_ftp(290, source="ramp_test", notes="Indoor ramp test")
        entry = FTPHistory.objects.get(user=user, ftp=290)
        assert entry.source == "ramp_test"
        assert entry.notes == "Indoor ramp test"

    def test_ftp_on_date_returns_effective_ftp(self, user):
        user.record_ftp(200, effective_date=datetime.date(2026, 1, 1))
        user.record_ftp(280, effective_date=datetime.date(2026, 6, 1))

        # Fixture seeded 250 at 2020-01-01, so pre-2020 returns None
        assert user.ftp_on_date(datetime.date(2019, 12, 31)) is None
        # Between fixture date and first explicit entry → fixture value
        assert user.ftp_on_date(datetime.date(2025, 6, 1)) == 250
        # After explicit entries → those values
        assert user.ftp_on_date(datetime.date(2026, 1, 1)) == 200
        assert user.ftp_on_date(datetime.date(2026, 2, 15)) == 200
        assert user.ftp_on_date(datetime.date(2026, 6, 1)) == 280
        assert user.ftp_on_date(datetime.date(2026, 12, 31)) == 280

    def test_ftp_on_date_before_first_entry_returns_none(self, db):
        """When date is before the first history entry, returns None."""
        u = User.objects.create_user(username="historyftp", password="test123")
        u.record_ftp(250, effective_date=datetime.date(2026, 3, 1))
        assert u.ftp_on_date(datetime.date(2026, 2, 1)) is None

    def test_ftp_no_history_returns_none(self, db):
        u = User.objects.create_user(username="noftp", password="test123")
        assert u.ftp is None
        assert u.ftp_on_date(datetime.date(2026, 3, 1)) is None


@pytest.mark.django_db
class TestWeightHistoryModel:
    def test_record_weight_creates_entry(self, user):
        user.record_weight(72.5, effective_date=datetime.date(2026, 3, 1))
        assert float(user.weight_kg) == 72.5
        assert WeightHistory.objects.filter(user=user).count() == 1

    def test_weight_returns_most_recent(self, user):
        user.record_weight(75.0, effective_date=datetime.date(2026, 1, 1))
        user.record_weight(71.0, effective_date=datetime.date(2026, 3, 1))
        assert float(user.weight_kg) == 71.0

    def test_weight_on_date(self, user):
        user.record_weight(75.0, effective_date=datetime.date(2026, 1, 1))
        user.record_weight(72.0, effective_date=datetime.date(2026, 3, 1))

        assert float(user.weight_on_date(datetime.date(2026, 2, 1))) == 75.0
        assert float(user.weight_on_date(datetime.date(2026, 4, 1))) == 72.0

    def test_weight_no_history_returns_none(self, db):
        u = User.objects.create_user(username="noweight", password="test123")
        assert u.weight_kg is None

    def test_watts_per_kg(self, user):
        user.record_ftp(280, effective_date=datetime.date(2026, 3, 1))
        user.record_weight(70.0, effective_date=datetime.date(2026, 3, 1))
        assert user.watts_per_kg == 4.0


# ── View tests ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestFTPHistoryViews:
    def test_ftp_history_page_requires_login(self, client):
        response = client.get(reverse("ftp_history"))
        assert response.status_code in (301, 302)
        assert "login" in response["Location"]

    def test_ftp_history_page_loads(self, auth_client):
        response = auth_client.get(reverse("ftp_history"))
        assert response.status_code == 200

    def test_add_ftp_entry(self, auth_client, user):
        response = auth_client.post(
            reverse("ftp_history"),
            {
                "add_ftp": "1",
                "ftp": 275,
                "effective_date": "2026-03-10",
                "source": "ramp_test",
                "notes": "Indoor ramp",
            },
        )
        assert response.status_code in (301, 302)
        assert FTPHistory.objects.filter(user=user, ftp=275).exists()
        assert user.ftp == 275

    def test_add_multiple_ftp_entries_in_order(self, auth_client, user):
        for ftp_val, date in [(240, "2026-01-01"), (260, "2026-02-01"), (280, "2026-03-01")]:
            auth_client.post(
                reverse("ftp_history"),
                {"add_ftp": "1", "ftp": ftp_val, "effective_date": date, "source": "manual"},
            )
        assert user.ftp == 280
        # 3 new + 1 from fixture
        assert FTPHistory.objects.filter(user=user).count() == 4

    def test_edit_ftp_entry(self, auth_client, user):
        user.record_ftp(250, effective_date=datetime.date(2026, 3, 1))
        entry = FTPHistory.objects.get(user=user, effective_date=datetime.date(2026, 3, 1))

        response = auth_client.post(
            reverse("ftp_history_edit", args=[entry.pk]),
            {
                "ftp": 265,
                "effective_date": "2026-03-01",
                "source": "20min_test",
                "notes": "Updated",
            },
        )
        assert response.status_code in (301, 302)

        entry.refresh_from_db()
        assert entry.ftp == 265
        assert entry.source == "20min_test"
        assert entry.notes == "Updated"

    def test_delete_ftp_entry(self, auth_client, user):
        user.record_ftp(280, effective_date=datetime.date(2026, 3, 1))
        user.record_ftp(260, effective_date=datetime.date(2026, 2, 1))
        entry_to_delete = FTPHistory.objects.get(
            user=user, effective_date=datetime.date(2026, 3, 1)
        )

        response = auth_client.post(reverse("ftp_history_delete", args=[entry_to_delete.pk]))
        assert response.status_code in (301, 302)

        # Most recent remaining should now be the Feb entry
        assert user.ftp == 260

    def test_delete_all_ftp_entries_clears_ftp(self, auth_client, db):
        u = User.objects.create_user(username="clearftp", password="testpass123")
        from apps.plans.models import UserProgressionScores

        UserProgressionScores.objects.create(user=u)
        auth_client.login(username="clearftp", password="testpass123")

        u.record_ftp(250, effective_date=datetime.date(2026, 3, 1))
        entry = FTPHistory.objects.get(user=u)
        auth_client.post(reverse("ftp_history_delete", args=[entry.pk]))
        assert u.ftp is None

    def test_cannot_edit_other_users_ftp(self, auth_client, db):
        other = User.objects.create_user(username="other", password="pass123")
        other.record_ftp(200, effective_date=datetime.date(2026, 3, 1))
        entry = FTPHistory.objects.get(user=other)

        response = auth_client.get(reverse("ftp_history_edit", args=[entry.pk]))
        assert response.status_code == 404

    def test_ftp_history_shows_entries(self, auth_client, user):
        user.record_ftp(270, effective_date=datetime.date(2026, 3, 1), source="ramp_test")

        response = auth_client.get(reverse("ftp_history"))
        content = response.content.decode()
        assert "270" in content
        assert "Ramp test" in content


@pytest.mark.django_db
class TestWeightHistoryViaProfile:
    def test_profile_save_records_weight_history(self, auth_client, user):
        """Saving a new weight via the profile form creates a WeightHistory entry."""
        auth_client.post(
            reverse("profile"),
            {"save_profile": "1", "weight_kg": "72.5"},
        )
        assert WeightHistory.objects.filter(user=user).count() == 1
        entry = WeightHistory.objects.get(user=user)
        assert float(entry.weight_kg) == 72.5

    def test_profile_save_same_weight_no_duplicate(self, auth_client, user):
        """Saving the same weight doesn't create a new history entry."""
        user.record_weight(72.5)

        auth_client.post(
            reverse("profile"),
            {"save_profile": "1", "weight_kg": "72.5"},
        )
        # Should still just be the one entry we manually created
        assert WeightHistory.objects.filter(user=user).count() == 1

    def test_profile_save_different_weight_adds_entry(self, auth_client, user):
        """Changing weight creates a new history entry."""
        user.record_weight(75.0, effective_date=datetime.date(2026, 3, 1))

        auth_client.post(
            reverse("profile"),
            {"save_profile": "1", "weight_kg": "72.5"},
        )
        # The new entry may overwrite today's date, or add a new one
        assert user.weight_kg is not None
        assert float(user.weight_kg) == 72.5


# ── TSS calculation uses FTP-on-date ──────────────────────────────────────────


@pytest.mark.django_db
class TestTSSUsesHistoricalFTP:
    def test_upsert_activity_uses_ftp_on_date(self, user):
        """_upsert_activity should use the FTP effective on the activity date."""
        from apps.integrations.strava.views import _upsert_activity

        user.record_ftp(200, effective_date=datetime.date(2026, 1, 1))
        user.record_ftp(300, effective_date=datetime.date(2026, 6, 1))

        # Activity in February → should use FTP 200
        raw = {
            "id": 12345,
            "name": "Feb Ride",
            "start_date": "2026-02-15T10:00:00Z",
            "moving_time": 3600,
            "distance": 40000,
            "total_elevation_gain": 500,
            "average_watts": 180,
            "weighted_average_watts": 190,
            "sport_type": "Ride",
            "type": "Ride",
            "average_heartrate": 145,
            "max_heartrate": 175,
            "kudos_count": 3,
        }
        _upsert_activity(user, raw)

        from apps.integrations.models import Activity

        act = Activity.objects.get(external_id="12345")
        # IF = NP / FTP = 190 / 200 = 0.95
        assert act.intensity_factor == 0.95

        # Activity in July → should use FTP 300
        raw2 = {
            **raw,
            "id": 12346,
            "name": "Jul Ride",
            "start_date": "2026-07-15T10:00:00Z",
        }
        _upsert_activity(user, raw2)
        act2 = Activity.objects.get(external_id="12346")
        # IF = NP / FTP = 190 / 300 = 0.633
        assert act2.intensity_factor == 0.633
