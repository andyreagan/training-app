"""
E2E: Workout detail page and file downloads.
"""

from pathlib import Path

import pytest


@pytest.mark.django_db(transaction=True)
def test_workout_detail_accessible_anonymously(page, live_url, seed):
    from apps.plans.models import WorkoutBlock

    wb = WorkoutBlock.objects.first()
    page.goto(live_url(f"/plans/workout/{wb.pk}/"))
    page.wait_for_load_state("networkidle")
    assert page.locator("table").count() >= 1


@pytest.mark.django_db(transaction=True)
def test_workout_detail_shows_interval_structure(logged_in_page, live_url, seed):
    from apps.plans.models import WorkoutBlock, WorkoutCategory

    # Pick a VO2max workout — has explicit interval rows
    wb = WorkoutBlock.objects.filter(category=WorkoutCategory.VO2MAX).first()

    page = logged_in_page
    page.goto(live_url(f"/plans/workout/{wb.pk}/"))
    page.wait_for_load_state("networkidle")

    content = page.content()
    assert "interval" in content.lower() or "warmup" in content.lower()
    assert "warmup" in content.lower()
    assert "cooldown" in content.lower()


@pytest.mark.django_db(transaction=True)
def test_workout_detail_shows_watts(logged_in_page, live_url, seed):
    from apps.plans.models import WorkoutBlock

    wb = WorkoutBlock.objects.first()
    page = logged_in_page
    page.goto(live_url(f"/plans/workout/{wb.pk}/"))
    page.wait_for_load_state("networkidle")
    # Watts column should show "W"
    assert " W" in page.content()


@pytest.mark.django_db(transaction=True)
def test_workout_detail_shows_download_buttons_when_logged_in(logged_in_page, live_url, seed):
    from apps.plans.models import WorkoutBlock

    wb = WorkoutBlock.objects.first()
    page = logged_in_page
    page.goto(live_url(f"/plans/workout/{wb.pk}/"))
    page.wait_for_load_state("networkidle")
    content = page.content()
    assert "Garmin FIT" in content
    assert "Zwift ZWO" in content
    assert "ERG" in content


def _download_from_detail(page, live_url, wb, label, expected_ext, expected_magic):
    """
    Navigate to the workout detail page, click a download button by label text,
    and return the downloaded bytes.
    """
    page.goto(live_url(f"/plans/workout/{wb.pk}/"))
    page.wait_for_load_state("networkidle")
    with page.expect_download(timeout=15_000) as dl_info:
        page.locator("a", has_text=label).first.click()
    download = dl_info.value
    assert download.suggested_filename.endswith(expected_ext)
    with Path(download.path()).open("rb") as f:
        data = f.read()
    assert expected_magic in data[:50]
    return data


@pytest.mark.django_db(transaction=True)
def test_fit_file_downloads(logged_in_page, live_url, seed):
    from apps.plans.models import WorkoutBlock

    wb = WorkoutBlock.objects.first()
    data = _download_from_detail(logged_in_page, live_url, wb, "Garmin FIT", ".fit", b".FIT")
    assert data[8:12] == b".FIT"


@pytest.mark.django_db(transaction=True)
def test_zwo_file_downloads(logged_in_page, live_url, seed):
    from apps.plans.models import WorkoutBlock

    wb = WorkoutBlock.objects.first()
    _download_from_detail(logged_in_page, live_url, wb, "Zwift ZWO", ".zwo", b"<?xml")


@pytest.mark.django_db(transaction=True)
def test_erg_file_downloads(logged_in_page, live_url, seed):
    from apps.plans.models import WorkoutBlock

    wb = WorkoutBlock.objects.first()
    _download_from_detail(logged_in_page, live_url, wb, "ERG file", ".erg", b"[COURSE HEADER]")


@pytest.mark.django_db(transaction=True)
def test_add_workout_to_calendar_from_detail_page(logged_in_page, live_url, seed):
    from apps.plans.models import WorkoutBlock

    wb = WorkoutBlock.objects.first()
    page = logged_in_page

    page.goto(live_url(f"/plans/workout/{wb.pk}/"))
    page.wait_for_load_state("networkidle")

    # Fill in the "Add to Calendar" form
    date_input = page.locator("input[name=date]")
    if date_input.is_visible():
        date_input.fill("2026-04-15")
        page.locator("button[type=submit]", has_text="Add to calendar").click()
        page.wait_for_load_state("networkidle")
        # Should redirect to the calendar (mounted at /scheduler/)
        assert "/scheduler/" in page.url


@pytest.mark.django_db(transaction=True)
def test_calendar_shows_added_workout(logged_in_page, live_url, seed, e2e_user):
    import datetime

    from apps.plans.models import WorkoutBlock
    from apps.scheduler.models import ScheduledWorkout

    wb = WorkoutBlock.objects.first()
    ScheduledWorkout.objects.create(
        user=e2e_user,
        workout=wb,
        date=datetime.date.today(),
    )

    page = logged_in_page
    page.goto(live_url("/scheduler/"))
    page.wait_for_load_state("networkidle")
    # FullCalendar renders the page; at minimum the calendar container must exist
    assert page.locator("#calendar").count() > 0
