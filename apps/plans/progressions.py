"""
Zone-based progression ladder system.

Design
──────
Each zone has an explicit ordered sequence of workouts ("rungs") defined by
Jem Arnold's Sustainable Training framework.  On top of this discrete ladder
sits a continuous score in [1.0, 10.0] — analogous to TrainerRoad's Progression
Levels.

The score and the ladder are related but separate:

  score  → float 1.0–10.0 stored per-user per-zone
  rung   → the discrete workout the score maps to

A score maps to the *highest rung whose threshold is ≤ the score*.  Thresholds
are manually assigned to each rung rather than linearly spaced because some
transitions are bigger jumps than others:

    VO2max: 4×4 min (score 1.0) → 4×5 min (2.0) → 3×6 min (3.5) → 4×6 min (4.5) …
             ↑ modest step              ↑ notable jump (6-min VO2max is qualitatively harder)

Within a rung, the fractional part of the score represents confidence /
adaptation margin.  A score of 3.7 means "solidly on rung 3, approaching rung 4."

    floor_score  = rung threshold  (score at which this rung becomes accessible)
    ceiling_score = next rung threshold (or 10.0 for last rung)

A "plain FTP" baseline (flat, no history) is assumed at score ≈ 5.0 for all zones,
which maps to the middle of each ladder.

Power values are % of the athlete's FTP.
Rest power valleys are light active recovery (35–52 % FTP).
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Power targets (% FTP) by zone ──────────────────────────────────────────────

ZONE_POWER: dict[str, tuple[int, int]] = {
    "recovery": (35, 55),
    "endurance": (56, 75),
    "tempo": (76, 87),
    "sweet_spot": (88, 93),
    "threshold": (95, 105),
    "vo2max": (106, 120),
    "anaerobic": (121, 150),
}

_REST_POWER = (35, 52)
_WARMUP_SEC = 10 * 60
_COOLDOWN_SEC = 10 * 60


# ── Rung ───────────────────────────────────────────────────────────────────────


@dataclass
class Rung:
    """One step on a zone's progression ladder."""

    score: float  # threshold score (1.0–10.0) at which this rung unlocks
    reps: int
    work_sec: int
    rest_sec: int = 0  # 0 = continuous / no structured rest
    note: str = ""

    @property
    def work_label(self) -> str:
        w = self.work_sec
        return f"{w // 60} min" if w >= 60 else f"{w} sec"

    @property
    def rest_label(self) -> str:
        r = self.rest_sec
        if r == 0:
            return "continuous"
        return f"{r // 60} min" if r >= 60 else f"{r} sec"

    def summary(self) -> str:
        if self.reps == 1 or self.rest_sec == 0:
            return f"{self.reps}×{self.work_label} (continuous)"
        return f"{self.reps}×{self.work_label} / {self.rest_label} rest"


# ── Ladders ────────────────────────────────────────────────────────────────────
#
# Threshold scores are non-uniform to reflect real difficulty jumps.
# The VO2max ladder mirrors Jem's example:
#     4×4 → 4×5 → 3×6 → 4×6 → 3×8 → 4×8 → 3×10 → 4×10
# Note: 4×5 → 3×6 is a larger jump than 3×6 → 4×6, reflected in the scores.
#
# Score ≈ 5.0 across all zones is the "plain FTP" baseline (middle of the ladder).

LADDERS: dict[str, list[Rung]] = {
    # ── Recovery ───────────────────────────────────────────────────────────────
    # Pure duration; cap at 60 min (longer defeats the purpose of recovery).
    "recovery": [
        Rung(1.0, 1, 20 * 60, note="Easy spin, stay below 55% FTP the whole time"),
        Rung(2.5, 1, 30 * 60),
        Rung(4.5, 1, 40 * 60),
        Rung(6.5, 1, 45 * 60),
        Rung(8.5, 1, 60 * 60, note="Cap at 60 min — longer risks becoming junk miles"),
    ],
    # ── Endurance (Z2) ─────────────────────────────────────────────────────────
    # Pure duration; the primary currency of Jem's framework.
    "endurance": [
        Rung(1.0, 1, 30 * 60, note="Foundation aerobic — fully conversational"),
        Rung(2.0, 1, 45 * 60),
        Rung(3.0, 1, 60 * 60),
        Rung(4.0, 1, 75 * 60),
        Rung(5.0, 1, 90 * 60),
        Rung(6.0, 1, 120 * 60),
        Rung(7.0, 1, 150 * 60),
        Rung(8.0, 1, 180 * 60),
        Rung(9.0, 1, 240 * 60),
        Rung(9.7, 1, 300 * 60, note="5-hour aerobic block — pacing and fueling mandatory"),
    ],
    # ── Tempo (Z3) ─────────────────────────────────────────────────────────────
    # Mostly continuous — tempo is sustained, not interval-y at higher PLs.
    "tempo": [
        Rung(1.0, 1, 20 * 60, note="Comfortably uncomfortable throughout"),
        Rung(2.0, 1, 25 * 60),
        Rung(3.0, 2, 15 * 60, 5 * 60),
        Rung(4.0, 1, 30 * 60),
        Rung(5.0, 2, 20 * 60, 4 * 60),
        Rung(6.0, 1, 40 * 60),
        Rung(7.0, 2, 25 * 60, 4 * 60),
        Rung(8.0, 1, 50 * 60),
        Rung(8.8, 2, 30 * 60, 3 * 60),
        Rung(9.5, 1, 60 * 60, note="Sustained 60-min tempo is a serious aerobic signal"),
    ],
    # ── Sweet Spot ─────────────────────────────────────────────────────────────
    # The highest-value zone in Jem's framework.  Progress = longer individual
    # efforts, not just more reps.  The jump to 15-min intervals is significant.
    "sweet_spot": [
        Rung(1.0, 3, 8 * 60, 5 * 60, note="Intro SS — short efforts, generous rest"),
        Rung(2.0, 3, 10 * 60, 4 * 60),
        Rung(3.2, 2, 15 * 60, 5 * 60, note="15-min SS is a meaningful step up"),
        Rung(4.0, 3, 12 * 60, 4 * 60),
        Rung(5.0, 2, 20 * 60, 4 * 60, note="Classic 2×20 — the benchmark SS workout"),
        Rung(6.0, 3, 15 * 60, 3 * 60),
        Rung(7.0, 2, 25 * 60, 3 * 60),
        Rung(7.8, 3, 20 * 60, 3 * 60),
        Rung(9.0, 1, 40 * 60, note="Continuous SS — strong muscular-aerobic load"),
        Rung(9.5, 1, 50 * 60),
        Rung(9.8, 1, 60 * 60, note="60-min continuous SS — top of the ladder"),
    ],
    # ── Threshold ──────────────────────────────────────────────────────────────
    # Hard.  Even a 1-min increase in interval duration matters a lot here.
    "threshold": [
        Rung(1.0, 3, 6 * 60, 5 * 60, note="Controlled, not desperate — dial it in"),
        Rung(2.0, 4, 6 * 60, 4 * 60),
        Rung(3.0, 3, 8 * 60, 4 * 60),
        Rung(4.0, 4, 8 * 60, 3 * 60),
        Rung(5.0, 3, 10 * 60, 3 * 60),
        Rung(5.8, 4, 10 * 60, 3 * 60),
        Rung(6.5, 3, 12 * 60, 3 * 60),
        Rung(7.2, 2, 15 * 60, 3 * 60, note="2×15 — a long time at FTP"),
        Rung(7.8, 3, 12 * 60, 2 * 60),
        Rung(8.5, 2, 20 * 60, 2 * 60),
        Rung(9.3, 1, 30 * 60, note="Continuous threshold — race-simulation effort"),
        Rung(9.8, 1, 40 * 60, note="Top of the ladder — race-winning fitness"),
    ],
    # ── VO2max ─────────────────────────────────────────────────────────────────
    # Jem's example progression: 4×4 → 4×5 → 3×6 → 4×6 → 3×8 → …
    # Longer single efforts are harder even when total volume drops.
    # Scores reflect this: the jump from 5-min to 6-min efforts scores bigger
    # than adding a 4th rep of the same 6-min effort.
    "vo2max": [
        Rung(1.0, 4, 4 * 60, 4 * 60, note="Entry VO2max — 1:1 work:rest ratio"),
        Rung(2.5, 4, 5 * 60, 4 * 60),
        Rung(4.0, 3, 6 * 60, 4 * 60, note="6-min efforts are a genuine step change"),
        Rung(5.5, 4, 6 * 60, 4 * 60),
        Rung(6.5, 3, 8 * 60, 4 * 60),
        Rung(7.5, 4, 8 * 60, 4 * 60),
        Rung(8.8, 3, 10 * 60, 4 * 60, note="10-min VO2max — elite-level demand"),
        Rung(9.7, 4, 10 * 60, 4 * 60),
    ],
    # ── Anaerobic ──────────────────────────────────────────────────────────────
    # Short, maximal.  Rest is generous — goal is max power output, not grinding.
    "anaerobic": [
        Rung(1.0, 6, 20, 2 * 60, note="Sprint quality over quantity — hit the power"),
        Rung(2.0, 8, 20, 2 * 60),
        Rung(3.0, 6, 30, 2 * 60),
        Rung(4.0, 8, 30, 90, note="Tighter rest — harder to maintain power targets"),
        Rung(5.0, 10, 30, 90),
        Rung(6.0, 6, 45, 90),
        Rung(7.0, 8, 45, 90),
        Rung(7.8, 6, 60, 2 * 60),
        Rung(8.8, 8, 60, 90),
        Rung(9.5, 6, 90, 2 * 60, note="90-sec anaerobic — exceptional neuromuscular demand"),
    ],
}


# ── Score ↔ rung mapping ───────────────────────────────────────────────────────


def rung_for_score(category: str, score: float) -> tuple[int, Rung]:
    """
    Return (step_number, Rung) for the highest rung whose threshold ≤ score.
    step_number is 1-based.  Clamps to the ladder bounds.
    """
    ladder = LADDERS.get(category)
    if not ladder:
        raise ValueError(f"Unknown category: {category!r}")
    score = max(ladder[0].score, min(10.0, score))
    active_step, active_rung = 1, ladder[0]
    for i, rung in enumerate(ladder):
        if rung.score <= score:
            active_step, active_rung = i + 1, rung
        else:
            break
    return active_step, active_rung


def score_for_step(category: str, step: int) -> float:
    """Return the threshold score for a given 1-based step number."""
    ladder = LADDERS.get(category, [])
    idx = max(0, min(step - 1, len(ladder) - 1))
    return ladder[idx].score


def ladder_length(category: str) -> int:
    return len(LADDERS.get(category, []))


def all_rungs(category: str) -> list[tuple[int, Rung]]:
    """Return [(step_number, Rung), …] for the full ladder."""
    return [(i + 1, r) for i, r in enumerate(LADDERS.get(category, []))]


def next_rung(category: str, score: float) -> tuple[int, Rung] | None:
    """
    Return (step_number, Rung) for the rung just above the current score,
    or None if already at the top.
    """
    ladder = LADDERS.get(category, [])
    for i, rung in enumerate(ladder):
        if rung.score > score:
            return i + 1, rung
    return None


# ── Structure computation ──────────────────────────────────────────────────────


def compute_structure(category: str, score: float) -> list[dict]:
    """
    Return the ordered list of step dicts for a workout at the given
    zone category and progression score.

    Step dict schema
    ────────────────
    type            : 'warmup' | 'cooldown' | 'steady' | 'interval'
    duration_seconds: int
    power_low       : int   (% FTP)
    power_high      : int   (% FTP)
    label           : str
    # interval-only fields:
    repeat                : int
    rest_duration_seconds : int
    rest_power_low        : int
    rest_power_high       : int
    """
    _, rung = rung_for_score(category, score)
    p_lo, p_hi = ZONE_POWER.get(category, (56, 75))
    r_lo, r_hi = _REST_POWER
    steps: list[dict] = []

    steps.append(
        {
            "type": "warmup",
            "duration_seconds": _WARMUP_SEC,
            "power_low": 40,
            "power_high": p_lo,
            "label": "Warm-up",
        }
    )

    is_continuous = rung.rest_sec == 0 or category in ("endurance", "recovery")
    if is_continuous:
        steps.append(
            {
                "type": "steady",
                "duration_seconds": rung.work_sec,
                "power_low": p_lo,
                "power_high": p_hi,
                "label": rung.summary(),
            }
        )
    else:
        steps.append(
            {
                "type": "interval",
                "repeat": rung.reps,
                "duration_seconds": rung.work_sec,
                "power_low": p_lo,
                "power_high": p_hi,
                "rest_duration_seconds": rung.rest_sec,
                "rest_power_low": r_lo,
                "rest_power_high": r_hi,
                "label": rung.summary(),
            }
        )

    steps.append(
        {
            "type": "cooldown",
            "duration_seconds": _COOLDOWN_SEC,
            "power_low": p_hi,
            "power_high": 40,
            "label": "Cool-down",
        }
    )

    return steps


def compute_total_duration_minutes(category: str, score: float) -> int:
    """Total clock time in minutes including warmup and cooldown."""
    total_sec = 0
    for s in compute_structure(category, score):
        reps = s.get("repeat", 1)
        total_sec += s["duration_seconds"] * reps
        total_sec += s.get("rest_duration_seconds", 0) * max(0, reps - 1)
    return round(total_sec / 60)


def compute_tss_estimate(category: str, score: float) -> int:
    """
    Estimate TSS at a reference FTP of 250 W.
    TSS = (t_sec × NP × IF) / (FTP × 3600) × 100
    """
    ftp = 250
    t_total = 0
    np4_sum = 0.0

    for s in compute_structure(category, score):
        avg_pct = (s["power_low"] + s["power_high"]) / 2
        avg_w = ftp * avg_pct / 100
        reps = s.get("repeat", 1)
        dur = s["duration_seconds"] * reps
        np4_sum += (avg_w**4) * dur
        t_total += dur

        if s.get("rest_duration_seconds") and reps > 1:
            r_pct = (s.get("rest_power_low", 35) + s.get("rest_power_high", 52)) / 2
            r_w = ftp * r_pct / 100
            r_dur = s["rest_duration_seconds"] * (reps - 1)
            np4_sum += (r_w**4) * r_dur
            t_total += r_dur

    if t_total == 0:
        return 0
    np = (np4_sum / t_total) ** 0.25
    if_ = np / ftp
    return round((t_total * np * if_) / (ftp * 3600) * 100)


def human_summary(category: str, score: float) -> str:
    """One-line description of the main set (skips warmup/cooldown)."""
    for s in compute_structure(category, score):
        if s["type"] == "steady":
            dur = s["duration_seconds"] // 60
            return f"{dur} min @ {s['power_low']}–{s['power_high']}% FTP"
        if s["type"] == "interval":
            reps = s.get("repeat", 1)
            dur = s["duration_seconds"]
            dur_s = f"{dur // 60} min" if dur >= 60 else f"{dur} sec"
            rest = s.get("rest_duration_seconds", 0)
            rest_s = f"{rest // 60} min" if rest >= 60 else f"{rest} sec"
            return f"{reps}×{dur_s} @ {s['power_low']}–{s['power_high']}% FTP / {rest_s} rest"
    return ""


def score_label(score: float) -> str:
    """Human label for a progression score."""
    if score < 2.0:
        return "Beginner"
    if score < 4.0:
        return "Novice"
    if score < 6.0:
        return "Intermediate"
    if score < 8.0:
        return "Advanced"
    if score < 9.5:
        return "Elite"
    return "World-class"
