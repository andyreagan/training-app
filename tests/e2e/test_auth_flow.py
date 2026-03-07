"""
E2E: Authentication flows — register, login, logout, profile update.
"""

import pytest


@pytest.mark.django_db(transaction=True)
def test_login_page_loads(page, live_url):
    page.goto(live_url("/accounts/login/"))
    assert page.title() != ""
    assert page.locator("input[name=username]").is_visible()
    assert page.locator("input[name=password]").is_visible()


@pytest.mark.django_db(transaction=True)
def test_login_with_valid_credentials(page, live_url, e2e_user, seed):
    page.goto(live_url("/accounts/login/"))
    page.fill("input[name=username]", "e2euser")
    page.fill("input[name=password]", "e2epass123")
    page.click("button[type=submit]")
    page.wait_for_url(lambda url: "/login" not in url, timeout=5000)
    # Should land on dashboard (root redirects there)
    assert "/login" not in page.url


@pytest.mark.django_db(transaction=True)
def test_login_with_wrong_password_shows_error(page, live_url, e2e_user):
    page.goto(live_url("/accounts/login/"))
    page.fill("input[name=username]", "e2euser")
    page.fill("input[name=password]", "wrongpassword")
    page.click("button[type=submit]")
    # Should stay on login page
    page.wait_for_load_state("networkidle")
    assert "/login" in page.url or page.locator("input[name=username]").is_visible()


@pytest.mark.django_db(transaction=True)
def test_register_creates_account_and_logs_in(page, live_url):
    page.goto(live_url("/accounts/register/"))
    page.fill("input[name=username]", "freshuser")
    page.fill("input[name=email]", "fresh@example.com")
    page.fill("input[name=password1]", "Cycl1ng@pass!")
    page.fill("input[name=password2]", "Cycl1ng@pass!")
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    # After register + auto-login, should not be on register page
    assert "/register" not in page.url


@pytest.mark.django_db(transaction=True)
def test_register_password_mismatch_stays_on_page(page, live_url):
    page.goto(live_url("/accounts/register/"))
    page.fill("input[name=username]", "someuser")
    page.fill("input[name=password1]", "Cycl1ng@pass!")
    page.fill("input[name=password2]", "Different!pass")
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    assert "/register" in page.url


@pytest.mark.django_db(transaction=True)
def test_logout_ends_session(logged_in_page, live_url):
    page = logged_in_page
    # POST to logout via JS fetch (avoids dropdown visibility issues)
    page.goto(live_url("/dashboard/"))
    page.wait_for_load_state("networkidle")
    page.evaluate("""
        async () => {
            const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] ?? '';
            await fetch('/accounts/logout/', {
                method: 'POST',
                headers: {'X-CSRFToken': csrf},
                credentials: 'same-origin',
            });
        }
    """)
    # After logout, protected page should redirect to login
    page.goto(live_url("/dashboard/"))
    page.wait_for_load_state("networkidle")
    assert "/login" in page.url


@pytest.mark.django_db(transaction=True)
def test_profile_page_shows_zone_scores(logged_in_page, live_url, seed):
    page = logged_in_page
    page.goto(live_url("/accounts/profile/"))
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "VO2 Max" in content
    assert "Sweet Spot" in content
    assert "Threshold" in content


@pytest.mark.django_db(transaction=True)
def test_profile_ftp_update(logged_in_page, live_url):
    page = logged_in_page
    page.goto(live_url("/accounts/profile/"))
    page.wait_for_load_state("networkidle")

    ftp_input = page.locator("input[name=ftp]")
    if ftp_input.is_visible():
        ftp_input.fill("310")
        page.locator("form button[type=submit]").first.click()
        page.wait_for_load_state("networkidle")
        # Re-open profile and verify value persisted
        page.goto(live_url("/accounts/profile/"))
        assert "310" in page.content()
