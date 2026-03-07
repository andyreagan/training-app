"""
View tests for the training calendar / scheduler.
"""

import datetime
import json

import pytest
from django.urls import reverse

from apps.scheduler.models import ScheduledWorkout


@pytest.mark.django_db
def test_calendar_requires_login(client):
    response = client.get(reverse("calendar"))
    assert response.status_code in (301, 302)
    assert "login" in response["Location"]


@pytest.mark.django_db
def test_calendar_returns_200(auth_client, user):
    response = auth_client.get(reverse("calendar"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_calendar_events_requires_login(client):
    response = client.get(reverse("calendar_events_api"))
    assert response.status_code in (301, 302)


@pytest.mark.django_db
def test_calendar_events_returns_json(auth_client, user):
    response = auth_client.get(reverse("calendar_events_api"))
    assert response.status_code == 200
    data = json.loads(response.content)
    assert isinstance(data, list)


@pytest.mark.django_db
def test_calendar_events_empty_for_new_user(auth_client, user):
    response = auth_client.get(reverse("calendar_events_api"))
    data = json.loads(response.content)
    assert data == []


@pytest.mark.django_db
def test_add_workout_via_json(auth_client, user, any_workout):
    today = datetime.date.today().isoformat()
    response = auth_client.post(
        reverse("add_workout"),
        data=json.dumps({"date": today, "workout_id": any_workout.pk}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = json.loads(response.content)
    assert data["start"] == today
    assert ScheduledWorkout.objects.filter(user=user, workout=any_workout).exists()


@pytest.mark.django_db
def test_add_workout_via_form_post(auth_client, user, any_workout):
    today = datetime.date.today().isoformat()
    response = auth_client.post(
        reverse("add_workout"),
        {"date": today, "workout_id": any_workout.pk, "notes": "morning"},
    )
    assert response.status_code in (301, 302)
    assert ScheduledWorkout.objects.filter(user=user, workout=any_workout).exists()


@pytest.mark.django_db
def test_add_workout_requires_login(client, any_workout):
    response = client.post(
        reverse("add_workout"),
        data=json.dumps({"date": "2026-03-01", "workout_id": any_workout.pk}),
        content_type="application/json",
    )
    assert response.status_code in (301, 302)


@pytest.mark.django_db
def test_calendar_events_returns_added_workout(auth_client, user, any_workout):
    today = datetime.date.today().isoformat()
    auth_client.post(
        reverse("add_workout"),
        data=json.dumps({"date": today, "workout_id": any_workout.pk}),
        content_type="application/json",
    )
    response = auth_client.get(reverse("calendar_events_api"))
    data = json.loads(response.content)
    assert len(data) == 1
    assert data[0]["start"] == today


@pytest.mark.django_db
def test_delete_workout(auth_client, user, any_workout):
    sw = ScheduledWorkout.objects.create(
        user=user,
        workout=any_workout,
        date=datetime.date.today(),
    )
    response = auth_client.post(reverse("delete_workout", kwargs={"pk": sw.pk}))
    assert response.status_code == 200
    assert not ScheduledWorkout.objects.filter(pk=sw.pk).exists()


@pytest.mark.django_db
def test_delete_workout_other_user_returns_404(auth_client, admin_user, any_workout):
    """Users cannot delete another user's scheduled workout."""
    other_sw = ScheduledWorkout.objects.create(
        user=admin_user,
        workout=any_workout,
        date=datetime.date.today(),
    )
    response = auth_client.post(reverse("delete_workout", kwargs={"pk": other_sw.pk}))
    assert response.status_code == 404


@pytest.mark.django_db
def test_move_workout(auth_client, user, any_workout):
    sw = ScheduledWorkout.objects.create(
        user=user,
        workout=any_workout,
        date=datetime.date.today(),
    )
    new_date = "2026-04-01"
    response = auth_client.post(
        reverse("move_workout", kwargs={"pk": sw.pk}),
        data=json.dumps({"date": new_date}),
        content_type="application/json",
    )
    assert response.status_code == 200
    sw.refresh_from_db()
    assert sw.date.isoformat() == new_date


@pytest.mark.django_db
def test_toggle_complete(auth_client, user, any_workout):
    sw = ScheduledWorkout.objects.create(
        user=user,
        workout=any_workout,
        date=datetime.date.today(),
        completed=False,
    )
    response = auth_client.post(reverse("toggle_complete", kwargs={"pk": sw.pk}))
    assert response.status_code == 200
    sw.refresh_from_db()
    assert sw.completed is True

    # Toggle again → back to False
    auth_client.post(reverse("toggle_complete", kwargs={"pk": sw.pk}))
    sw.refresh_from_db()
    assert sw.completed is False
