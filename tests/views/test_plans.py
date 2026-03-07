"""
View tests for plan browsing, adoption, and workout detail.
"""

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_plan_list_anonymous_200(client, seeded_plans):
    response = client.get(reverse("plan_list"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_plan_list_shows_plan_name(client, seeded_plans):
    response = client.get(reverse("plan_list"))
    assert b"Sustainable Training" in response.content


@pytest.mark.django_db
def test_plan_detail_anonymous_200(client, seeded_plans):
    response = client.get(reverse("plan_detail", kwargs={"slug": "sustainable-training"}))
    assert response.status_code == 200


@pytest.mark.django_db
def test_plan_detail_404_for_unknown_slug(client, seeded_plans):
    response = client.get(reverse("plan_detail", kwargs={"slug": "does-not-exist"}))
    assert response.status_code == 404


@pytest.mark.django_db
def test_plan_detail_shows_weekly_rows(client, seeded_plans):
    response = client.get(reverse("plan_detail", kwargs={"slug": "sustainable-training"}))
    content = response.content.decode()
    assert "Week 1" in content


@pytest.mark.django_db
def test_workout_detail_anonymous_200(client, any_workout):
    response = client.get(reverse("workout_detail", kwargs={"pk": any_workout.pk}))
    assert response.status_code == 200


@pytest.mark.django_db
def test_workout_detail_shows_structure(client, any_workout):
    response = client.get(reverse("workout_detail", kwargs={"pk": any_workout.pk}))
    content = response.content.decode()
    # Warmup and cooldown should always appear
    assert "warmup" in content.lower() or "Warm" in content
    assert "cooldown" in content.lower() or "Cool" in content


@pytest.mark.django_db
def test_workout_detail_shows_download_links(auth_client, any_workout):
    response = auth_client.get(reverse("workout_detail", kwargs={"pk": any_workout.pk}))
    content = response.content.decode()
    assert "Garmin FIT" in content
    assert "Zwift ZWO" in content
    assert "ERG" in content


@pytest.mark.django_db
def test_adopt_plan_requires_login(client, seeded_plans):
    response = client.post(
        reverse("adopt_plan", kwargs={"slug": "sustainable-training"}),
        {"start_date": "2026-03-01"},
    )
    assert response.status_code in (301, 302)
    assert "login" in response["Location"]


@pytest.mark.django_db
def test_adopt_plan_creates_user_plan(auth_client, user, seeded_plans):
    from apps.plans.models import UserPlan
    assert not UserPlan.objects.filter(user=user).exists()

    response = auth_client.post(
        reverse("adopt_plan", kwargs={"slug": "sustainable-training"}),
        {"start_date": "2026-03-01"},
    )
    assert response.status_code in (301, 302)
    assert UserPlan.objects.filter(user=user, is_active=True).exists()


@pytest.mark.django_db
def test_adopt_plan_deactivates_previous_plan(auth_client, user, seeded_plans):
    from apps.plans.models import UserPlan
    # Adopt once
    auth_client.post(
        reverse("adopt_plan", kwargs={"slug": "sustainable-training"}),
        {"start_date": "2026-01-01"},
    )
    # Adopt again with new date
    auth_client.post(
        reverse("adopt_plan", kwargs={"slug": "sustainable-training"}),
        {"start_date": "2026-03-01"},
    )
    active = UserPlan.objects.filter(user=user, is_active=True)
    assert active.count() == 1


@pytest.mark.django_db
def test_unadopt_plan_requires_login(client, seeded_plans):
    response = client.post(
        reverse("unadopt_plan", kwargs={"slug": "sustainable-training"})
    )
    assert response.status_code in (301, 302)
    assert "login" in response["Location"]


@pytest.mark.django_db
def test_unadopt_plan_deactivates(auth_client, user, seeded_plans):
    from apps.plans.models import UserPlan
    UserPlan.objects.create(
        user=user,
        plan=seeded_plans,
        start_date="2026-01-01",
        is_active=True,
    )
    response = auth_client.post(
        reverse("unadopt_plan", kwargs={"slug": "sustainable-training"})
    )
    assert response.status_code in (301, 302)
    assert not UserPlan.objects.filter(user=user, is_active=True).exists()


# ── Download views ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
@pytest.mark.parametrize("fmt,content_type,magic", [
    ("fit", "application/octet-stream", b".FIT"),
    ("zwo", "application/xml",          b"<?xml"),
    ("erg", "text/plain",               b"[COURSE HEADER]"),
])
def test_download_workout_returns_correct_content(auth_client, any_workout, fmt, content_type, magic):
    response = auth_client.get(
        reverse("download_workout", kwargs={"pk": any_workout.pk, "fmt": fmt})
    )
    assert response.status_code == 200
    assert content_type in response["Content-Type"]
    assert response.content[:len(magic)] == magic or magic in response.content[:50]


@pytest.mark.django_db
def test_download_workout_requires_login(client, any_workout):
    response = client.get(
        reverse("download_workout", kwargs={"pk": any_workout.pk, "fmt": "fit"})
    )
    assert response.status_code in (301, 302)


@pytest.mark.django_db
def test_download_workout_404_for_unknown_format(auth_client, any_workout):
    response = auth_client.get(
        reverse("download_workout", kwargs={"pk": any_workout.pk, "fmt": "csv"})
    )
    assert response.status_code == 404
