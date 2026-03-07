"""
E2E conftest: fixtures that combine pytest-django's live_server
with pytest-playwright's page fixture.

Key design decisions
────────────────────
- All E2E tests use @pytest.mark.django_db(transaction=True) so the live_server
  thread can see data created in the test thread.
- `live_url` is a tiny helper that makes tests read cleanly:
      page.goto(live_url("/accounts/login/"))
- `logged_in_page` handles the login flow once and returns a ready page.
"""

import pytest
from django.core.management import call_command


# ── Seed fixture ───────────────────────────────────────────────────────────────

@pytest.fixture
def seed(db):
    """Seed workout blocks + plans, return the TrainingPlan."""
    call_command("seed_plans", verbosity=0)
    from apps.plans.models import TrainingPlan
    return TrainingPlan.objects.get(slug="sustainable-training")


# ── URL helper ─────────────────────────────────────────────────────────────────

@pytest.fixture
def live_url(live_server):
    """Return a callable: live_url('/path/') → full URL string."""
    def _url(path: str) -> str:
        return live_server.url + path
    return _url


# ── User + login helpers ───────────────────────────────────────────────────────

@pytest.fixture
def e2e_user(db):
    """A test user with FTP and progression scores, for E2E tests."""
    from django.contrib.auth import get_user_model
    from apps.plans.models import UserProgressionScores

    User = get_user_model()
    u = User.objects.create_user(
        username="e2euser",
        email="e2e@example.com",
        password="e2epass123",
        ftp=250,
    )
    UserProgressionScores.objects.create(user=u)
    return u


@pytest.fixture
def logged_in_page(page, live_url, e2e_user):
    """
    A Playwright page already logged in as e2euser.
    Navigates to login, fills credentials, submits, waits for dashboard.
    """
    page.goto(live_url("/accounts/login/"))
    page.fill("input[name=username]", "e2euser")
    page.fill("input[name=password]", "e2epass123")
    page.click("button[type=submit]")
    # Wait until we're past the login page
    page.wait_for_url(lambda url: "/login" not in url, timeout=5000)
    return page
