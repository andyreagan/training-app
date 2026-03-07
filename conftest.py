"""
Root pytest conftest — fixtures shared across all test layers.
"""

import os

import pytest
from django.contrib.auth import get_user_model

# pytest-playwright starts an async event loop internally; without this,
# Django raises SynchronousOnlyOperation when it tries to set up the test DB.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


# ── Users ──────────────────────────────────────────────────────────────────────

@pytest.fixture
def user(db):
    """An authenticated user with FTP set and default progression scores."""
    User = get_user_model()
    u = User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
        ftp=250,
    )
    from apps.plans.models import UserProgressionScores
    UserProgressionScores.objects.create(user=u)
    return u


@pytest.fixture
def admin_user(db):
    """A superuser for admin-level tests."""
    User = get_user_model()
    return User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="adminpass123",
    )


@pytest.fixture
def auth_client(client, user):
    """A Django test client already logged in as `user`."""
    client.login(username="testuser", password="testpass123")
    return client


# ── Plan data ──────────────────────────────────────────────────────────────────

@pytest.fixture
def seeded_plans(db):
    """
    Seed all workout blocks and the Sustainable Training plan.
    Idempotent — safe to call multiple times in a session.
    Returns the TrainingPlan instance.
    """
    from django.core.management import call_command
    call_command("seed_plans", verbosity=0)
    from apps.plans.models import TrainingPlan
    return TrainingPlan.objects.get(slug="sustainable-training")


@pytest.fixture
def any_workout(seeded_plans):
    """Any seeded WorkoutBlock — useful when the specific workout doesn't matter."""
    from apps.plans.models import WorkoutBlock
    return WorkoutBlock.objects.first()
