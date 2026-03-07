"""
Unit tests for apps/plans/progressions.py.

No database access — pure logic.
"""

import pytest

from apps.plans.progressions import (
    LADDERS,
    ZONE_POWER,
    all_rungs,
    compute_structure,
    compute_total_duration_minutes,
    compute_tss_estimate,
    human_summary,
    ladder_length,
    next_rung,
    rung_for_score,
    score_for_step,
    score_label,
)

ALL_CATEGORIES = list(LADDERS.keys())
EXPECTED_CATEGORIES = {
    "recovery", "endurance", "tempo", "sweet_spot",
    "threshold", "vo2max", "anaerobic",
}


# ── Ladder structure ───────────────────────────────────────────────────────────

@pytest.mark.unit
def test_all_expected_categories_present():
    assert set(LADDERS.keys()) == EXPECTED_CATEGORIES


@pytest.mark.unit
def test_all_categories_have_power_targets():
    assert set(ZONE_POWER.keys()) == EXPECTED_CATEGORIES


@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_ladder_scores_are_sorted(cat):
    scores = [r.score for r in LADDERS[cat]]
    assert scores == sorted(scores), f"{cat}: rung scores not in ascending order"


@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_ladder_scores_are_unique(cat):
    scores = [r.score for r in LADDERS[cat]]
    assert len(scores) == len(set(scores)), f"{cat}: duplicate rung scores"


@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_ladder_scores_in_range(cat):
    for rung in LADDERS[cat]:
        assert 1.0 <= rung.score <= 10.0, (
            f"{cat}: score {rung.score} out of [1.0, 10.0]"
        )


@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_ladder_first_score_is_1(cat):
    assert LADDERS[cat][0].score == 1.0, f"{cat}: first rung must start at score 1.0"


@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_ladder_has_at_least_3_rungs(cat):
    assert len(LADDERS[cat]) >= 3, f"{cat}: need at least 3 rungs"


@pytest.mark.unit
def test_vo2max_ladder_matches_jem():
    """Verify the exact VO2max progression Jem describes in sparecycles.blog."""
    ladder = LADDERS["vo2max"]
    expected = [
        (4, 4 * 60),   # 4×4 min
        (4, 5 * 60),   # 4×5 min
        (3, 6 * 60),   # 3×6 min
        (4, 6 * 60),   # 4×6 min
        (3, 8 * 60),   # 3×8 min
        (4, 8 * 60),   # 4×8 min
        (3, 10 * 60),  # 3×10 min
        (4, 10 * 60),  # 4×10 min
    ]
    assert len(ladder) == len(expected)
    for rung, (reps, work_sec) in zip(ladder, expected):
        assert rung.reps == reps
        assert rung.work_sec == work_sec


# ── rung_for_score ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_rung_for_score_returns_first_rung_at_min():
    step, rung = rung_for_score("vo2max", 1.0)
    assert step == 1
    assert rung.reps == 4
    assert rung.work_sec == 4 * 60


@pytest.mark.unit
def test_rung_for_score_clamps_below_minimum():
    step, rung = rung_for_score("vo2max", 0.0)
    assert step == 1  # clamped to first rung


@pytest.mark.unit
def test_rung_for_score_clamps_above_maximum():
    step, rung = rung_for_score("vo2max", 99.0)
    assert step == ladder_length("vo2max")  # last rung


@pytest.mark.unit
def test_rung_for_score_at_threshold_boundary():
    # Score exactly at 4.0 → 3rd VO2max rung (3×6 min)
    step, rung = rung_for_score("vo2max", 4.0)
    assert rung.reps == 3
    assert rung.work_sec == 6 * 60


@pytest.mark.unit
def test_rung_for_score_just_below_threshold():
    # Score 3.99 → still 2nd rung (4×5 min)
    step, rung = rung_for_score("vo2max", 3.99)
    assert rung.reps == 4
    assert rung.work_sec == 5 * 60


@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_rung_for_score_default_5_is_valid(cat):
    step, rung = rung_for_score(cat, 5.0)
    assert step >= 1
    assert step <= ladder_length(cat)
    assert rung is not None


# ── Ladder utility functions ───────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_ladder_length_matches_ladders(cat):
    assert ladder_length(cat) == len(LADDERS[cat])


@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_all_rungs_step_numbers_are_1_indexed(cat):
    rungs = all_rungs(cat)
    assert [s for s, _ in rungs] == list(range(1, len(LADDERS[cat]) + 1))


@pytest.mark.unit
def test_score_for_step_first():
    assert score_for_step("vo2max", 1) == 1.0


@pytest.mark.unit
def test_next_rung_returns_none_at_top():
    top_score = LADDERS["vo2max"][-1].score
    assert next_rung("vo2max", top_score) is None


@pytest.mark.unit
def test_next_rung_returns_next_rung():
    step, rung = next_rung("vo2max", 1.0)
    assert rung.score == LADDERS["vo2max"][1].score


# ── compute_structure ──────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_structure_has_warmup_and_cooldown(cat):
    steps = compute_structure(cat, 5.0)
    types = [s["type"] for s in steps]
    assert types[0] == "warmup"
    assert types[-1] == "cooldown"


@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_structure_has_at_least_3_steps(cat):
    steps = compute_structure(cat, 5.0)
    assert len(steps) >= 3  # warmup + main + cooldown


@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_structure_all_steps_have_required_keys(cat):
    required = {"type", "duration_seconds", "power_low", "power_high"}
    for step in compute_structure(cat, 5.0):
        assert required <= step.keys(), f"{cat}: step missing keys: {step}"


@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_structure_power_values_are_positive(cat):
    for step in compute_structure(cat, 5.0):
        assert step["power_low"] > 0
        assert step["power_high"] > 0
        # Warmup/cooldown are ramps and may be descending (power_low > power_high).
        # Only interval/steady steps must be non-descending.
        if step["type"] in ("interval", "steady"):
            assert step["power_high"] >= step["power_low"]


@pytest.mark.unit
def test_interval_zone_produces_interval_step():
    steps = compute_structure("vo2max", 5.0)
    main_steps = [s for s in steps if s["type"] not in ("warmup", "cooldown")]
    assert any(s["type"] == "interval" for s in main_steps)


@pytest.mark.unit
def test_interval_step_has_rest_fields():
    steps = compute_structure("vo2max", 5.0)
    for step in steps:
        if step["type"] == "interval":
            assert "repeat" in step
            assert "rest_duration_seconds" in step
            assert step["repeat"] >= 1


@pytest.mark.unit
def test_endurance_produces_steady_step():
    steps = compute_structure("endurance", 5.0)
    main_steps = [s for s in steps if s["type"] not in ("warmup", "cooldown")]
    assert any(s["type"] == "steady" for s in main_steps)


# ── Duration and TSS ──────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_total_duration_is_positive(cat):
    assert compute_total_duration_minutes(cat, 5.0) > 0


@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_total_duration_includes_warmup_cooldown(cat):
    # Warmup + cooldown = 20 min; total must be > 20
    assert compute_total_duration_minutes(cat, 5.0) > 20


@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_tss_estimate_is_positive(cat):
    assert compute_tss_estimate(cat, 5.0) > 0


@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_tss_is_plausible(cat):
    tss = compute_tss_estimate(cat, 5.0)
    # Very few workouts are < 10 TSS or > 400 TSS
    assert 10 <= tss <= 400, f"{cat}: TSS {tss} outside plausible range"


# ── human_summary / score_label ───────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("cat", ALL_CATEGORIES)
def test_human_summary_is_non_empty(cat):
    assert len(human_summary(cat, 5.0)) > 0


@pytest.mark.unit
@pytest.mark.parametrize("score,expected", [
    (1.0, "Beginner"),
    (1.9, "Beginner"),
    (2.0, "Novice"),
    (3.9, "Novice"),
    (4.0, "Intermediate"),
    (5.9, "Intermediate"),
    (6.0, "Advanced"),
    (7.9, "Advanced"),
    (8.0, "Elite"),
    (9.4, "Elite"),
    (9.5, "World-class"),
    (10.0, "World-class"),
])
def test_score_label(score, expected):
    assert score_label(score) == expected
