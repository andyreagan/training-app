"""
Workout difficulty prediction engine.

Pure Python — no Django imports.  Predicts how hard a workout will feel
for a specific athlete on a specific day, expressed as a probability
distribution over 5 difficulty levels.

The prediction is driven by two factors:

  1. Score gap — how the workout's progression score compares to the
     user's current score in that zone.  A workout above your level
     is harder; one below is easier.

  2. Fatigue — the athlete's TSB (Training Stress Balance) on the day
     of the workout.  Negative TSB shifts everything toward harder.

The model is a softmax over 5 levels with a location parameter.  This
is a simple parametric model designed to be swapped out for something
learned from real data later — the input/output interface stays the same.

Difficulty levels
─────────────────
  1 — Easy:       well within your abilities, minimal challenge
  2 — Moderate:   achievable with focus, some discomfort
  3 — Hard:       demanding, requires commitment to complete
  4 — Very Hard:  at the edge of your ability, high chance of failure
  5 — Stretch:    likely to fail or require modification
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DIFFICULTY_LABELS = {
    1: "Easy",
    2: "Moderate",
    3: "Hard",
    4: "Very Hard",
    5: "Stretch",
}

DIFFICULTY_COLORS = {
    1: "#4ade80",  # green
    2: "#a3e635",  # lime
    3: "#facc15",  # yellow
    4: "#fb923c",  # orange
    5: "#ef4444",  # red
}


@dataclass
class DifficultyPrediction:
    """A probability distribution over 5 difficulty levels."""

    probabilities: dict[int, float]  # {1: 0.05, 2: 0.15, 3: 0.50, 4: 0.25, 5: 0.05}
    expected: float  # weighted mean (e.g. 3.1)
    label: str  # label for the most probable level

    @property
    def most_likely(self) -> int:
        """The difficulty level with the highest probability."""
        return max(self.probabilities, key=self.probabilities.get)

    @property
    def most_likely_label(self) -> str:
        return DIFFICULTY_LABELS[self.most_likely]

    @property
    def most_likely_pct(self) -> int:
        return round(self.probabilities[self.most_likely] * 100)

    def to_dict(self) -> dict:
        """Serialize for JSON API responses."""
        return {
            "levels": [
                {
                    "level": level,
                    "label": DIFFICULTY_LABELS[level],
                    "probability": round(prob, 3),
                    "pct": round(prob * 100),
                    "color": DIFFICULTY_COLORS[level],
                }
                for level, prob in sorted(self.probabilities.items())
            ],
            "expected": round(self.expected, 1),
            "label": self.label,
        }


def predict(
    workout_score: float,
    user_score: float,
    tsb: float = 0.0,
    intended_effort: int = 5,
) -> DifficultyPrediction:
    """
    Predict workout difficulty as a probability distribution.

    Parameters
    ----------
    workout_score
        The workout's progression_score (1.0–10.0).
    user_score
        The user's current progression score for this zone (1.0–10.0).
    tsb
        Training Stress Balance on the workout day.  Positive = fresh,
        negative = fatigued.
    intended_effort
        The workout's prescribed RPE (1–10).  Higher intended effort
        shifts the distribution toward harder.

    Returns
    -------
    DifficultyPrediction
    """
    # ── Score gap: primary driver ──────────────────────────────────────────
    # Positive gap = workout is above user's level = harder.
    # Each 1.0 of score gap shifts difficulty by ~1 level.
    score_gap = workout_score - user_score

    # ── Fatigue adjustment ────────────────────────────────────────────────
    # TSB of -30 adds about +1 level of difficulty.
    # TSB of +20 subtracts about -0.5 levels.
    fatigue_shift = -tsb / 30.0

    # ── Effort adjustment ─────────────────────────────────────────────────
    # Intended effort above 5 (the midpoint) pushes toward harder.
    # Scale: effort 10 → +0.5 shift, effort 1 → -0.5 shift.
    effort_shift = (intended_effort - 5) * 0.1

    # ── Combine into a location parameter ─────────────────────────────────
    # Center = 3.0 (Hard) when gap=0, fresh, moderate effort.
    center = 3.0 + score_gap + fatigue_shift + effort_shift

    # ── Softmax over 5 levels ─────────────────────────────────────────────
    # Temperature controls spread — lower = more peaked.
    temperature = 0.8
    levels = [1, 2, 3, 4, 5]
    logits = [-((level - center) ** 2) / (2 * temperature**2) for level in levels]

    # Stable softmax
    max_logit = max(logits)
    exp_logits = [math.exp(logit - max_logit) for logit in logits]
    total = sum(exp_logits)
    probs = {level: exp_logits[i] / total for i, level in enumerate(levels)}

    # ── Expected value ────────────────────────────────────────────────────
    expected = sum(level * prob for level, prob in probs.items())

    # ── Label from most likely level ──────────────────────────────────────
    most_likely = max(probs, key=probs.get)
    label = DIFFICULTY_LABELS[most_likely]

    return DifficultyPrediction(
        probabilities=probs,
        expected=expected,
        label=label,
    )
