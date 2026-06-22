"""
Unit / model-layer tests for apps/plans/models.py.

These touch the database (WorkoutBlock and UserProgressionScores are DB models)
but contain no HTTP requests.
"""

import pytest

from apps.plans.models import (
    UserProgressionScores,
    WorkoutBlock,
    WorkoutCategory,
)
from apps.plans.progressions import LADDERS

# ── WorkoutBlock ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_workout_block_color_is_hex(seeded_plans):
    wb = WorkoutBlock.objects.first()
    assert wb.color.startswith("#")
    assert len(wb.color) == 7


@pytest.mark.django_db
def test_workout_block_category_label(seeded_plans):
    wb = WorkoutBlock.objects.filter(category=WorkoutCategory.VO2MAX).first()
    assert wb.category_label == "VO2 Max"


@pytest.mark.django_db
def test_workout_block_structure_is_non_empty(seeded_plans):
    for wb in WorkoutBlock.objects.all()[:5]:
        assert len(wb.structure) >= 3  # warmup + main + cooldown


@pytest.mark.django_db
def test_workout_block_structure_has_warmup_cooldown(seeded_plans):
    wb = WorkoutBlock.objects.first()
    types = [s["type"] for s in wb.structure]
    assert types[0] == "warmup"
    assert types[-1] == "cooldown"


@pytest.mark.django_db
def test_workout_block_total_duration_cached_on_save(seeded_plans):
    wb = WorkoutBlock.objects.first()
    assert wb.total_duration_minutes > 0


@pytest.mark.django_db
def test_workout_block_tss_cached_on_save(seeded_plans):
    wb = WorkoutBlock.objects.first()
    assert wb.tss_estimate > 0


@pytest.mark.django_db
def test_workout_block_summary_is_non_empty(seeded_plans):
    wb = WorkoutBlock.objects.first()
    assert len(wb.summary) > 0


@pytest.mark.django_db
def test_workout_block_score_label_non_empty(seeded_plans):
    wb = WorkoutBlock.objects.first()
    assert len(wb.score_label) > 0


@pytest.mark.django_db
def test_workout_block_zone_power_returns_tuple(seeded_plans):
    wb = WorkoutBlock.objects.first()
    lo, hi = wb.zone_power
    assert 0 < lo < hi <= 200


@pytest.mark.django_db
def test_workout_block_structure_with_watts_scales_ftp(seeded_plans):
    wb = WorkoutBlock.objects.filter(category=WorkoutCategory.VO2MAX).first()
    steps250 = wb.structure_with_watts(250)
    steps300 = wb.structure_with_watts(300)
    # At least one step must have higher watts at 300W FTP
    watts250 = [s.get("watts_high", 0) for s in steps250]
    watts300 = [s.get("watts_high", 0) for s in steps300]
    assert any(w300 > w250 for w250, w300 in zip(watts250, watts300, strict=True))


@pytest.mark.django_db
def test_all_seeded_blocks_have_unique_slugs(seeded_plans):
    slugs = list(WorkoutBlock.objects.values_list("slug", flat=True))
    assert len(slugs) == len(set(slugs))


@pytest.mark.django_db
def test_seeded_block_count(seeded_plans):
    """seed_plans should produce exactly 66 workout blocks (all ladder rungs)."""
    total_rungs = sum(len(rungs) for rungs in LADDERS.values())
    assert WorkoutBlock.objects.count() == total_rungs


@pytest.mark.django_db
def test_workout_block_rung_property(seeded_plans):
    wb = WorkoutBlock.objects.filter(category="vo2max").first()
    rung = wb.rung
    assert rung is not None
    assert rung.reps > 0
    assert rung.work_sec > 0


# ── UserProgressionScores ──────────────────────────────────────────────────────


@pytest.mark.django_db
def test_user_progression_scores_defaults_to_5(user):
    scores = user.progression_scores
    for cat in UserProgressionScores.SCORE_FIELDS:
        assert scores.score_for(cat) == 5.0


@pytest.mark.django_db
def test_user_progression_scores_as_dict_has_all_zones(user):
    d = user.progression_scores.as_dict()
    expected = set(UserProgressionScores.SCORE_FIELDS.keys())
    assert set(d.keys()) == expected


@pytest.mark.django_db
def test_set_score_clamps_to_range(user):
    scores = user.progression_scores
    scores.set_score("vo2max", 0.0)
    assert scores.score_for("vo2max") == 1.0
    scores.set_score("vo2max", 99.0)
    assert scores.score_for("vo2max") == 10.0


@pytest.mark.django_db
def test_rung_summary_has_all_zones(user, seeded_plans):
    summary = user.progression_scores.rung_summary()
    assert set(summary.keys()) == set(UserProgressionScores.SCORE_FIELDS.keys())


@pytest.mark.django_db
def test_rung_summary_required_keys(user, seeded_plans):
    summary = user.progression_scores.rung_summary()
    required = {"zone_label", "score", "score_label", "step", "total_steps", "summary", "note"}
    for cat, info in summary.items():
        assert required <= info.keys(), f"{cat}: missing keys {required - info.keys()}"


@pytest.mark.django_db
def test_rung_summary_step_is_in_range(user, seeded_plans):
    summary = user.progression_scores.rung_summary()
    for cat, info in summary.items():
        assert 1 <= info["step"] <= info["total_steps"], (
            f"{cat}: step {info['step']} out of [1, {info['total_steps']}]"
        )


@pytest.mark.django_db
def test_rung_summary_next_is_none_at_top(user, seeded_plans):
    scores = user.progression_scores
    scores.set_score("vo2max", 10.0)
    scores.save()
    summary = scores.rung_summary()
    assert summary["vo2max"]["next_score"] is None
    assert summary["vo2max"]["next_summary"] is None
