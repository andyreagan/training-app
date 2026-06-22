"""
Banister impulse-response model for training load tracking.

Implements the classic CTL / ATL / TSB model:

  CTL (Chronic Training Load, "fitness")
      Exponentially weighted moving average of daily TSS, τ = 42 days.

  ATL (Acute Training Load, "fatigue")
      Exponentially weighted moving average of daily TSS, τ = 7 days.

  TSB (Training Stress Balance, "form")
      TSB = CTL − ATL.  Positive = fresh, negative = fatigued.

This module is intentionally Django-free.  It takes plain Python data in
and returns plain Python data out, so it can be unit-tested without a
database.

Reference
─────────
Banister et al. (1975).  "A systems model of training for athletic
performance."  Australian Journal of Sports Medicine 7:57–61.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Literal


@dataclass
class DayMetrics:
    """One day's training load numbers."""

    date: datetime.date
    tss: float
    ctl: float
    atl: float
    tsb: float
    source: Literal["actual", "planned", "rest"]


@dataclass
class TSSInput:
    """A single day's TSS value fed into the model."""

    date: datetime.date
    tss: float
    source: Literal["actual", "planned", "rest"] = "actual"


# ── TSB zone thresholds ────────────────────────────────────────────────────────
#
# These map to the TrainerRoad-style day coloring:
#   fresh   : TSB > 15     → green  (ready to perform)
#   neutral : -10 < TSB ≤ 15 → grey   (normal training)
#   tired   : -30 < TSB ≤ -10 → yellow (accumulating fatigue)
#   danger  : TSB ≤ -30    → red    (overreaching, injury risk)

TSB_ZONES = {
    "fresh": 15,
    "neutral": -10,
    "tired": -30,
}


def tsb_zone(tsb: float) -> str:
    """Return the zone label for a TSB value."""
    if tsb > TSB_ZONES["fresh"]:
        return "fresh"
    if tsb > TSB_ZONES["neutral"]:
        return "neutral"
    if tsb > TSB_ZONES["tired"]:
        return "tired"
    return "danger"


def tsb_color(tsb: float) -> str:
    """Return a hex color for a TSB value, suitable for calendar day backgrounds."""
    zone = tsb_zone(tsb)
    return {
        "fresh": "#d4edda",  # green
        "neutral": "#e9ecef",  # grey
        "tired": "#fff3cd",  # yellow
        "danger": "#f8d7da",  # red
    }[zone]


# ── Core computation ──────────────────────────────────────────────────────────


def compute(
    daily_tss: list[TSSInput],
    ctl_tau: float = 42.0,
    atl_tau: float = 7.0,
    initial_ctl: float = 0.0,
    initial_atl: float = 0.0,
) -> list[DayMetrics]:
    """
    Run the Banister model over a series of daily TSS values.

    Parameters
    ----------
    daily_tss
        List of TSSInput, one per day.  Gaps are allowed — they will be
        filled with TSS=0 ("rest" source).  Does not need to be sorted.
    ctl_tau
        Time constant for CTL (chronic / fitness).  Default 42 days.
    atl_tau
        Time constant for ATL (acute / fatigue).  Default 7 days.
    initial_ctl
        Starting CTL on the day before the first input.
    initial_atl
        Starting ATL on the day before the first input.

    Returns
    -------
    list[DayMetrics]
        One entry per day from the earliest to the latest input date,
        inclusive, sorted by date.
    """
    if not daily_tss:
        return []

    # Build a date→(tss, source) map, handling duplicates by summing
    by_date: dict[datetime.date, tuple[float, str]] = {}
    for inp in daily_tss:
        if inp.date in by_date:
            existing_tss, existing_source = by_date[inp.date]
            # Sum TSS; prefer "actual" source over "planned"
            merged_source = (
                "actual" if existing_source == "actual" or inp.source == "actual" else inp.source
            )
            by_date[inp.date] = (existing_tss + inp.tss, merged_source)
        else:
            by_date[inp.date] = (inp.tss, inp.source)

    start = min(by_date)
    end = max(by_date)

    ctl_decay = 1.0 - 1.0 / ctl_tau
    atl_decay = 1.0 - 1.0 / atl_tau
    ctl_gain = 1.0 / ctl_tau
    atl_gain = 1.0 / atl_tau

    ctl = initial_ctl
    atl = initial_atl
    result: list[DayMetrics] = []
    day = start

    while day <= end:
        if day in by_date:
            tss, source = by_date[day]
        else:
            tss, source = 0.0, "rest"

        ctl = ctl * ctl_decay + tss * ctl_gain
        atl = atl * atl_decay + tss * atl_gain
        tsb = ctl - atl

        result.append(
            DayMetrics(
                date=day,
                tss=tss,
                ctl=round(ctl, 1),
                atl=round(atl, 1),
                tsb=round(tsb, 1),
                source=source,
            )
        )
        day += datetime.timedelta(days=1)

    return result
