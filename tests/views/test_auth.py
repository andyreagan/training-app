"""
View tests for authentication: login, register, logout, profile.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse


@pytest.mark.django_db
def test_login_page_get(client):
    response = client.get(reverse("login"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_register_page_get(client):
    response = client.get(reverse("register"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_login_with_valid_credentials(client, user):
    response = client.post(
        reverse("login"),
        {
            "username": "testuser",
            "password": "testpass123",
        },
    )
    # Should redirect (to dashboard or next param)
    assert response.status_code in (301, 302)


@pytest.mark.django_db
def test_login_with_invalid_credentials(client):
    response = client.post(
        reverse("login"),
        {
            "username": "nobody",
            "password": "wrongpass",
        },
    )
    assert response.status_code == 200  # re-renders form


@pytest.mark.django_db
def test_register_creates_user_and_redirects(client):
    User = get_user_model()
    assert not User.objects.filter(username="newrider").exists()
    response = client.post(
        reverse("register"),
        {
            "username": "newrider",
            "password1": "str0ngP@ss!",
            "password2": "str0ngP@ss!",
            "email": "newrider@example.com",
        },
    )
    assert response.status_code in (301, 302)
    assert User.objects.filter(username="newrider").exists()


@pytest.mark.django_db
def test_register_with_mismatched_passwords_returns_200(client):
    response = client.post(
        reverse("register"),
        {
            "username": "newrider",
            "password1": "str0ngP@ss!",
            "password2": "different!",
        },
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_profile_requires_login(client):
    response = client.get(reverse("profile"))
    assert response.status_code in (301, 302)
    assert "login" in response["Location"]


@pytest.mark.django_db
def test_profile_returns_200_when_logged_in(auth_client, user, seeded_plans):
    response = auth_client.get(reverse("profile"))
    assert response.status_code == 200


@pytest.mark.django_db
def test_profile_contains_zone_names(auth_client, user, seeded_plans):
    response = auth_client.get(reverse("profile"))
    content = response.content.decode()
    assert "VO2 Max" in content
    assert "Sweet Spot" in content
    assert "Threshold" in content


@pytest.mark.django_db
def test_profile_post_updates_weight(auth_client, user):
    response = auth_client.post(
        reverse("profile"),
        {
            "save_profile": "1",
            "weight_kg": "70.0",
        },
    )
    assert response.status_code in (301, 302)
    assert user.weight_kg == 70.0


@pytest.mark.django_db
def test_ftp_history_add(auth_client, user):
    """Adding an FTP entry via the history page sets User.ftp."""
    response = auth_client.post(
        reverse("ftp_history"),
        {
            "add_ftp": "1",
            "ftp": 300,
            "effective_date": "2026-03-16",
            "source": "manual",
            "notes": "Ramp test",
        },
    )
    assert response.status_code in (301, 302)
    assert user.ftp == 300


@pytest.mark.django_db
def test_logout_redirects(auth_client):
    response = auth_client.post(reverse("logout"))
    assert response.status_code in (301, 302)


@pytest.mark.django_db
def test_dashboard_requires_login(client):
    response = client.get(reverse("dashboard"))
    assert response.status_code in (301, 302)


@pytest.mark.django_db
def test_dashboard_returns_200_when_logged_in(auth_client, user, seeded_plans):
    response = auth_client.get(reverse("dashboard"))
    assert response.status_code == 200
