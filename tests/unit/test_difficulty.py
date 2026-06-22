"""
Unit tests for the difficulty prediction engine.

Pure math — no database, no Django ORM.
"""

from apps.difficulty.predict import (
    DIFFICULTY_LABELS,
    DifficultyPrediction,
    predict,
)


class TestPredictBasics:
    """Core properties that must hold regardless of parameters."""

    def test_returns_prediction(self):
        pred = predict(workout_score=5.0, user_score=5.0)
        assert isinstance(pred, DifficultyPrediction)

    def test_probabilities_sum_to_one(self):
        pred = predict(workout_score=5.0, user_score=5.0)
        total = sum(pred.probabilities.values())
        assert abs(total - 1.0) < 1e-9

    def test_all_five_levels_present(self):
        pred = predict(workout_score=5.0, user_score=5.0)
        assert set(pred.probabilities.keys()) == {1, 2, 3, 4, 5}

    def test_all_probabilities_non_negative(self):
        pred = predict(workout_score=5.0, user_score=5.0)
        assert all(p >= 0 for p in pred.probabilities.values())

    def test_expected_in_range(self):
        pred = predict(workout_score=5.0, user_score=5.0)
        assert 1.0 <= pred.expected <= 5.0

    def test_label_is_valid(self):
        pred = predict(workout_score=5.0, user_score=5.0)
        assert pred.label in DIFFICULTY_LABELS.values()

    def test_to_dict_structure(self):
        pred = predict(workout_score=5.0, user_score=5.0)
        d = pred.to_dict()
        assert "levels" in d
        assert "expected" in d
        assert "label" in d
        assert len(d["levels"]) == 5
        for entry in d["levels"]:
            assert set(entry.keys()) == {"level", "label", "probability", "pct", "color"}


class TestScoreGap:
    """Workout score relative to user score is the primary driver."""

    def test_at_level_centers_on_hard(self):
        """When workout matches user's score, most likely is ~3 (Hard)."""
        pred = predict(workout_score=5.0, user_score=5.0)
        assert pred.most_likely == 3

    def test_below_level_is_easier(self):
        """Workout well below user's score should be Easy or Moderate."""
        pred = predict(workout_score=2.0, user_score=7.0)
        assert pred.most_likely <= 2
        assert pred.expected < 2.0

    def test_above_level_is_harder(self):
        """Workout well above user's score should be Very Hard or Stretch."""
        pred = predict(workout_score=8.0, user_score=3.0)
        assert pred.most_likely >= 4
        assert pred.expected > 4.0

    def test_slightly_above_shifts_up(self):
        """A small positive gap shifts toward harder."""
        at_level = predict(workout_score=5.0, user_score=5.0)
        slightly_above = predict(workout_score=6.0, user_score=5.0)
        assert slightly_above.expected > at_level.expected

    def test_slightly_below_shifts_down(self):
        """A small negative gap shifts toward easier."""
        at_level = predict(workout_score=5.0, user_score=5.0)
        slightly_below = predict(workout_score=4.0, user_score=5.0)
        assert slightly_below.expected < at_level.expected

    def test_monotonic_with_gap(self):
        """Expected difficulty should increase monotonically with score gap."""
        results = []
        for gap in [-3, -2, -1, 0, 1, 2, 3]:
            pred = predict(workout_score=5.0 + gap, user_score=5.0)
            results.append(pred.expected)
        for i in range(len(results) - 1):
            assert results[i] <= results[i + 1] + 0.01  # allow tiny float noise


class TestFatigue:
    """TSB (fatigue) shifts difficulty independent of score gap."""

    def test_fatigued_is_harder(self):
        """Negative TSB should make the same workout feel harder."""
        fresh = predict(workout_score=5.0, user_score=5.0, tsb=20.0)
        tired = predict(workout_score=5.0, user_score=5.0, tsb=-30.0)
        assert tired.expected > fresh.expected

    def test_fresh_is_easier(self):
        """Positive TSB should make the same workout feel easier."""
        neutral = predict(workout_score=5.0, user_score=5.0, tsb=0.0)
        fresh = predict(workout_score=5.0, user_score=5.0, tsb=25.0)
        assert fresh.expected < neutral.expected

    def test_deep_fatigue_pushes_toward_stretch(self):
        """Extreme fatigue should push toward level 5."""
        deep = predict(workout_score=5.0, user_score=5.0, tsb=-60.0)
        assert deep.expected > 4.0

    def test_fatigue_effect_is_gradual(self):
        """The effect should increase smoothly with fatigue depth."""
        values = []
        for tsb in [30, 10, 0, -10, -30, -50]:
            pred = predict(workout_score=5.0, user_score=5.0, tsb=float(tsb))
            values.append(pred.expected)
        for i in range(len(values) - 1):
            assert values[i] <= values[i + 1] + 0.01


class TestEffort:
    """Intended effort modulates difficulty prediction."""

    def test_high_effort_shifts_up(self):
        """A VO2max workout (effort 9) should feel harder than endurance (effort 4)."""
        easy = predict(workout_score=5.0, user_score=5.0, intended_effort=4)
        hard = predict(workout_score=5.0, user_score=5.0, intended_effort=9)
        assert hard.expected > easy.expected

    def test_effort_effect_is_modest(self):
        """Effort should be a secondary factor — score gap dominates."""
        low = predict(workout_score=5.0, user_score=5.0, intended_effort=1)
        high = predict(workout_score=5.0, user_score=5.0, intended_effort=10)
        # The difference should be meaningful but not huge (< 1.5 levels)
        assert high.expected - low.expected < 1.5
        assert high.expected - low.expected > 0.3


class TestCombinedFactors:
    """Test interactions between multiple factors."""

    def test_easy_workout_when_fresh_and_below_level(self):
        pred = predict(workout_score=3.0, user_score=7.0, tsb=20.0, intended_effort=3)
        assert pred.most_likely == 1
        assert pred.probabilities[1] > 0.5

    def test_stretch_when_fatigued_and_above_level(self):
        pred = predict(workout_score=8.0, user_score=4.0, tsb=-30.0, intended_effort=9)
        assert pred.most_likely == 5
        assert pred.probabilities[5] > 0.5

    def test_hard_at_level_neutral_fatigue(self):
        pred = predict(workout_score=5.0, user_score=5.0, tsb=0.0, intended_effort=5)
        assert pred.most_likely == 3
        assert pred.expected > 2.5
        assert pred.expected < 3.5

    def test_probabilities_always_valid(self):
        """Sweep a wide range of inputs — probabilities must always be valid."""
        for ws in [1.0, 3.0, 5.0, 7.0, 10.0]:
            for us in [1.0, 3.0, 5.0, 7.0, 10.0]:
                for tsb in [-50, -20, 0, 20, 50]:
                    for effort in [1, 5, 10]:
                        pred = predict(
                            workout_score=ws,
                            user_score=us,
                            tsb=float(tsb),
                            intended_effort=effort,
                        )
                        total = sum(pred.probabilities.values())
                        assert abs(total - 1.0) < 1e-9
                        assert all(p >= 0 for p in pred.probabilities.values())
                        assert 1.0 <= pred.expected <= 5.0


class TestProperties:
    """Test DifficultyPrediction convenience properties."""

    def test_most_likely(self):
        pred = predict(workout_score=5.0, user_score=5.0)
        ml = pred.most_likely
        assert ml in [1, 2, 3, 4, 5]
        assert pred.probabilities[ml] == max(pred.probabilities.values())

    def test_most_likely_label(self):
        pred = predict(workout_score=5.0, user_score=5.0)
        assert pred.most_likely_label in DIFFICULTY_LABELS.values()

    def test_most_likely_pct(self):
        pred = predict(workout_score=5.0, user_score=5.0)
        pct = pred.most_likely_pct
        assert 0 <= pct <= 100
