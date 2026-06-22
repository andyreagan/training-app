"""
Tests for demo mode:
  - /demo/ auto-login view
  - DemoModeMiddleware (blocks writes, allows reads)
  - setup_demo management command
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

User = get_user_model()

DEMO_USERNAME = "demo"
DEMO_PASSWORD = "demo1234"


# ── fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def demo_user(db):
    """Create a minimal demo user (no seeded data — unit tests don't need it)."""
    u = User.objects.create_user(
        username=DEMO_USERNAME,
        password=DEMO_PASSWORD,
        email="demo@example.com",
        max_hr=185,
        resting_hr=52,
    )
    import datetime

    u.record_ftp(250, effective_date=datetime.date(2025, 1, 1))
    return u


@pytest.fixture
def demo_client(demo_user):
    c = Client()
    c.login(username=DEMO_USERNAME, password=DEMO_PASSWORD)
    return c


# ── /demo/ auto-login view ─────────────────────────────────────────────────────


class TestDemoLoginView:
    def test_redirects_to_dashboard(self, demo_user, client):
        resp = client.get("/demo/")
        assert resp.status_code == 302
        assert resp["Location"] in ("/dashboard/", "http://testserver/dashboard/")

    def test_logs_in_demo_user(self, demo_user, client):
        client.get("/demo/")
        resp = client.get("/dashboard/")
        assert resp.status_code == 200

    def test_already_demo_redirects(self, demo_client):
        resp = demo_client.get("/demo/")
        assert resp.status_code == 302

    def test_missing_demo_user_shows_error(self, db, client):
        """If demo user doesn't exist, /demo/ should show an error and redirect."""
        resp = client.get("/demo/")
        assert resp.status_code == 302
        assert "login" in resp["Location"]

    def test_logs_out_existing_session_first(self, demo_user, user, client):
        """A real user visiting /demo/ should be swapped to demo session."""
        client.force_login(user)
        resp = client.get("/demo/")
        assert resp.status_code == 302
        # Should now be the demo user
        client.get("/dashboard/")
        session_user = client.session.get("_auth_user_id")
        assert str(demo_user.pk) == session_user


# ── DemoModeMiddleware ─────────────────────────────────────────────────────────


class TestDemoModeMiddleware:
    def test_is_demo_true_for_demo_user(self, demo_client):
        """request.is_demo should be True — banner should appear."""
        resp = demo_client.get("/dashboard/")
        assert resp.status_code == 200
        assert b"demo-banner" in resp.content

    def test_is_demo_false_for_real_user(self, client, user):
        client.force_login(user)
        resp = client.get("/dashboard/")
        assert b"demo-banner" not in resp.content

    def test_is_demo_false_for_anonymous(self, client):
        resp = client.get("/accounts/login/")
        assert b"demo-banner" not in resp.content

    def test_demo_user_can_post(self, demo_client):
        """Demo users are NOT blocked — they can make changes freely."""
        resp = demo_client.post("/accounts/profile/", data={"save_profile": "1"})
        # Profile form submission should process normally (redirect on success/invalid)
        assert resp.status_code in (200, 302)

    def test_demo_user_can_get(self, demo_client):
        resp = demo_client.get("/dashboard/")
        assert resp.status_code == 200

    def test_login_works_for_demo(self, demo_user, client):
        resp = client.post(
            "/accounts/login/",
            data={"username": DEMO_USERNAME, "password": DEMO_PASSWORD},
        )
        assert resp.status_code == 302

    def test_logout_works_for_demo(self, demo_client):
        resp = demo_client.post("/accounts/logout/")
        assert resp.status_code == 302


# ── setup_demo management command ─────────────────────────────────────────────


class TestSetupDemoCommand:
    def test_creates_demo_user(self, db):
        from django.core.management import call_command

        # Need at least some workout blocks for schedule seeding
        # (progressions command not run here — just check user creation)
        call_command("setup_demo", "--quiet")

        u = User.objects.get(username=DEMO_USERNAME)
        assert u.check_password(DEMO_PASSWORD)
        assert u.max_hr == 185
        assert u.resting_hr == 52

    def test_seeds_ftp_history(self, db):
        from django.core.management import call_command

        call_command("setup_demo", "--quiet")

        u = User.objects.get(username=DEMO_USERNAME)
        assert u.ftp_history.count() == 3
        assert u.ftp == 251

    def test_seeds_weight_history(self, db):
        from django.core.management import call_command

        call_command("setup_demo", "--quiet")

        u = User.objects.get(username=DEMO_USERNAME)
        assert u.weight_history.count() == 4

    def test_seeds_activities(self, db):
        from django.core.management import call_command

        from apps.integrations.models import Activity

        call_command("setup_demo", "--quiet")

        u = User.objects.get(username=DEMO_USERNAME)
        count = Activity.objects.filter(user=u).count()
        assert count > 20  # should be ~30–45

    def test_activities_have_power_and_hr_streams(self, db):
        from django.core.management import call_command

        from apps.integrations.models import Activity

        call_command("setup_demo", "--quiet")

        u = User.objects.get(username=DEMO_USERNAME)
        acts = Activity.objects.filter(user=u, power_data__isnull=False)
        assert acts.count() > 0
        act = acts.first()
        assert "watts" in act.power_data
        assert "heartrate" in act.hr_data

    def test_activities_have_tss(self, db):
        from django.core.management import call_command

        from apps.integrations.models import Activity

        call_command("setup_demo", "--quiet")

        u = User.objects.get(username=DEMO_USERNAME)
        # All activities should have TSS (power-based)
        missing = Activity.objects.filter(user=u, tss__isnull=True).count()
        assert missing == 0

    def test_idempotent(self, db):
        """Running setup_demo twice should not duplicate data."""
        from django.core.management import call_command

        from apps.integrations.models import Activity

        call_command("setup_demo", "--quiet")
        first_count = Activity.objects.filter(user=User.objects.get(username=DEMO_USERNAME)).count()

        call_command("setup_demo", "--quiet")
        second_count = Activity.objects.filter(
            user=User.objects.get(username=DEMO_USERNAME)
        ).count()

        assert first_count == second_count

    def test_seeds_progression_scores(self, db):
        from django.core.management import call_command

        from apps.plans.models import UserProgressionScores

        call_command("setup_demo", "--quiet")

        u = User.objects.get(username=DEMO_USERNAME)
        scores, _ = UserProgressionScores.objects.get_or_create(user=u)
        assert scores.score_for("endurance") == 6.5
        assert scores.score_for("threshold") == 4.0
