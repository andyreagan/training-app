"""
E2E: Plan browsing, adoption, and calendar population.
"""

import pytest


@pytest.mark.django_db(transaction=True)
def test_plan_list_shows_sustainable_training(logged_in_page, live_url, seed):
    page = logged_in_page
    page.goto(live_url("/plans/"))
    page.wait_for_load_state("networkidle")
    assert "Sustainable Training" in page.content()


@pytest.mark.django_db(transaction=True)
def test_plan_list_accessible_anonymously(page, live_url, seed):
    page.goto(live_url("/plans/"))
    page.wait_for_load_state("networkidle")
    assert page.locator("text=Sustainable Training").count() > 0


@pytest.mark.django_db(transaction=True)
def test_navigate_to_plan_detail(logged_in_page, live_url, seed):
    page = logged_in_page
    page.goto(live_url("/plans/"))
    page.wait_for_load_state("networkidle")
    # The plan list shows a "View plan" link for each plan
    page.locator("a", has_text="View plan").first.click()
    page.wait_for_load_state("networkidle")
    assert "/plans/" in page.url
    assert "Week 1" in page.content()


@pytest.mark.django_db(transaction=True)
def test_plan_detail_shows_day_columns(logged_in_page, live_url, seed):
    page = logged_in_page
    page.goto(live_url("/plans/sustainable-training/"))
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "Mon" in content
    assert "Sat" in content


@pytest.mark.django_db(transaction=True)
def test_adopt_plan_via_modal(logged_in_page, live_url, seed):
    page = logged_in_page
    page.goto(live_url("/plans/sustainable-training/"))
    page.wait_for_load_state("networkidle")

    # Click "Start this plan" button to open modal
    start_btn = page.locator("button", has_text="Start this plan")
    assert start_btn.is_visible()
    start_btn.click()

    # Modal should appear
    modal = page.locator("#adoptModal")
    modal.wait_for(state="visible", timeout=3000)

    # Set a start date and submit
    page.fill("#adoptModal input[name=start_date]", "2026-04-01")
    page.locator("#adoptModal button[type=submit]").click()
    page.wait_for_load_state("networkidle")

    # Should redirect to the calendar (mounted at /scheduler/)
    assert "/scheduler/" in page.url


@pytest.mark.django_db(transaction=True)
def test_adopted_plan_shows_active_badge(logged_in_page, live_url, seed, e2e_user):
    import datetime

    from apps.plans.models import TrainingPlan, UserPlan

    plan = TrainingPlan.objects.get(slug="sustainable-training")
    UserPlan.objects.create(user=e2e_user, plan=plan, start_date=datetime.date.today())

    page = logged_in_page
    page.goto(live_url("/plans/sustainable-training/"))
    page.wait_for_load_state("networkidle")
    content = page.content()
    # Should show the "active" state — populate calendar / remove buttons
    assert "Populate calendar" in content or "Remove" in content


@pytest.mark.django_db(transaction=True)
def test_nav_links_present(logged_in_page, live_url, seed):
    page = logged_in_page
    page.goto(live_url("/dashboard/"))
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "Plans" in content
    assert "Calendar" in content
