"""
Power curve and FTP estimation engine.

Pure Python — no Django imports.  Takes raw watts arrays in, returns
analysis results out.

Key concepts
────────────
Mean-maximal power curve:
    For each duration d from 1 s to the full ride length, the highest
    average power sustained for any contiguous d-second window.  This is
    the standard "power curve" or "power-duration curve."

FTP estimation:
    Classic method: best 20-minute power × 0.95.
    If 60+ minutes of data exist, also report best 60-minute power
    (which should approximate FTP directly).

    Works on both single-activity raw watts and merged multi-activity
    power curves.

Rolling average:
    A simple moving average used to smooth the raw power trace for
    display.  Not the same as NP (which uses a 30-s rolling average
    raised to the 4th power).
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field


@dataclass
class PowerCurvePoint:
    """One point on the mean-maximal power curve."""

    duration_seconds: int
    watts: float


@dataclass
class FTPEstimate:
    """An FTP estimate derived from a power curve."""

    ftp: int
    method: str  # "20min_95pct" or "60min_best"
    duration_seconds: int
    raw_power: float  # the actual best power for that duration


# ── Rolling average ───────────────────────────────────────────────────────────


def compute_rolling_average(
    watts: list[int | float],
    window_seconds: int = 30,
    sample_rate: int = 1,
) -> list[float]:
    """
    Compute a simple moving average of the power trace.

    Parameters
    ----------
    watts : list
        Raw power values, one per sample.
    window_seconds : int
        Smoothing window in seconds.
    sample_rate : int
        Samples per second (1 for 1-Hz data, which is standard).

    Returns
    -------
    list[float]
        Smoothed power values, same length as input.  The first
        ``window - 1`` values use a shorter window (expanding).
    """
    if not watts:
        return []

    window = window_seconds * sample_rate
    n = len(watts)
    result = [0.0] * n

    # Prefix sum for O(n) sliding window
    prefix = [0.0] * (n + 1)
    for i in range(n):
        prefix[i + 1] = prefix[i] + watts[i]

    for i in range(n):
        lo = max(0, i - window + 1)
        count = i - lo + 1
        result[i] = round((prefix[i + 1] - prefix[lo]) / count, 1)

    return result


# ── Mean-maximal power curve ──────────────────────────────────────────────────


# Standard durations to sample (seconds).  These are the conventional
# points shown on a power curve chart.  We always compute them plus
# the full ride duration.
CURVE_DURATIONS = [
    1,
    2,
    5,
    10,
    15,
    20,
    30,
    45,
    60,
    90,
    120,
    180,
    240,
    300,
    360,
    480,
    600,
    720,
    900,
    1200,
    1800,
    2400,
    3600,
    4800,
    5400,
    7200,
]


def compute_power_curve(
    watts: list[int | float],
    sample_rate: int = 1,
    durations: list[int] | None = None,
) -> list[PowerCurvePoint]:
    """
    Compute the mean-maximal power curve.

    For each target duration, finds the highest average power over any
    contiguous window of that length.

    Parameters
    ----------
    watts : list
        Raw power values at ``sample_rate`` Hz.
    sample_rate : int
        Samples per second.
    durations : list[int], optional
        Specific durations (in seconds) to compute.  Defaults to
        ``CURVE_DURATIONS`` filtered to the ride length.

    Returns
    -------
    list[PowerCurvePoint]
        Sorted by duration ascending.
    """
    if not watts:
        return []

    n = len(watts)
    total_seconds = n // sample_rate

    if durations is None:
        durations = [d for d in CURVE_DURATIONS if d <= total_seconds]
        # Always include the full ride
        if total_seconds not in durations and total_seconds > 0:
            durations.append(total_seconds)
        durations.sort()

    if not durations:
        return []

    # Prefix sum for O(n) per duration
    prefix = [0.0] * (n + 1)
    for i in range(n):
        prefix[i + 1] = prefix[i] + watts[i]

    result: list[PowerCurvePoint] = []
    for dur_sec in durations:
        window = dur_sec * sample_rate
        if window > n:
            continue

        best = 0.0
        for i in range(window, n + 1):
            avg = (prefix[i] - prefix[i - window]) / window
            if avg > best:
                best = avg

        result.append(
            PowerCurvePoint(
                duration_seconds=dur_sec,
                watts=round(best, 1),
            )
        )

    return result


# ── FTP estimation ────────────────────────────────────────────────────────────


def estimate_ftp(
    watts: list[int | float],
    sample_rate: int = 1,
) -> FTPEstimate | None:
    """
    Estimate FTP from a power trace.

    Uses the classic 95% of best 20-minute power.  If the ride is 60+
    minutes, also computes best 60-minute power and returns whichever
    method gives the lower (more conservative) estimate.

    Returns None if the ride is shorter than 20 minutes.
    """
    n = len(watts)
    total_seconds = n // sample_rate

    if total_seconds < 20 * 60:
        return None

    # Compute the specific durations we need
    needed = [20 * 60]
    if total_seconds >= 60 * 60:
        needed.append(60 * 60)

    curve = compute_power_curve(watts, sample_rate=sample_rate, durations=needed)
    curve_by_dur = {p.duration_seconds: p.watts for p in curve}

    best_20 = curve_by_dur.get(20 * 60)
    best_60 = curve_by_dur.get(60 * 60)

    estimates: list[FTPEstimate] = []

    if best_20:
        estimates.append(
            FTPEstimate(
                ftp=round(best_20 * 0.95),
                method="20min_95pct",
                duration_seconds=20 * 60,
                raw_power=best_20,
            )
        )

    if best_60:
        estimates.append(
            FTPEstimate(
                ftp=round(best_60),
                method="60min_best",
                duration_seconds=60 * 60,
                raw_power=best_60,
            )
        )

    if not estimates:
        return None

    # Return the more conservative (lower) estimate
    return min(estimates, key=lambda e: e.ftp)


# ── Multi-activity power profile ──────────────────────────────────────────────


@dataclass
class ActivityCurveInput:
    """Power curve from a single activity, with metadata for attribution."""

    date: datetime.date
    activity_name: str
    curve: list[PowerCurvePoint]
    perceived_effort: int | None = None
    tsb: float | None = None


@dataclass
class MergedCurvePoint:
    """One point on the merged (best-of-all-activities) power curve."""

    duration_seconds: int
    watts: float
    source_date: datetime.date
    source_name: str


@dataclass
class PowerProfile:
    """A merged power curve across multiple activities with FTP estimate."""

    curve: list[MergedCurvePoint]
    ftp_estimate: FTPEstimate | None
    activity_count: int
    date_range: tuple[datetime.date, datetime.date]
    # Per-activity curves for overlay display
    activity_curves: list[ActivityCurveInput] = field(default_factory=list)


def merge_power_curves(
    activity_inputs: list[ActivityCurveInput],
) -> list[MergedCurvePoint]:
    """
    Merge multiple per-activity power curves into a single best-of curve.

    For each duration, keeps the highest watts across all activities,
    with attribution to which activity it came from.

    Parameters
    ----------
    activity_inputs
        List of ActivityCurveInput, each containing a power curve
        from a single activity.

    Returns
    -------
    list[MergedCurvePoint]
        Sorted by duration ascending.  One point per unique duration
        seen across all input curves.
    """
    if not activity_inputs:
        return []

    # For each duration, track the best watts and which activity it came from
    best: dict[int, tuple[float, datetime.date, str]] = {}
    for inp in activity_inputs:
        for point in inp.curve:
            existing = best.get(point.duration_seconds)
            if existing is None or point.watts > existing[0]:
                best[point.duration_seconds] = (point.watts, inp.date, inp.activity_name)

    result = [
        MergedCurvePoint(
            duration_seconds=dur,
            watts=round(watts, 1),
            source_date=src_date,
            source_name=src_name,
        )
        for dur, (watts, src_date, src_name) in sorted(best.items())
    ]
    return result


def estimate_ftp_from_curve(
    curve: list[PowerCurvePoint] | list[MergedCurvePoint],
) -> FTPEstimate | None:
    """
    Estimate FTP from a pre-computed power curve (single or merged).

    Uses the same logic as ``estimate_ftp`` but works from a curve
    rather than raw watts, so it can be applied to merged multi-activity
    curves.

    Returns None if the curve doesn't contain a 20-minute data point.
    """
    curve_by_dur = {p.duration_seconds: p.watts for p in curve}

    best_20 = curve_by_dur.get(20 * 60)
    best_60 = curve_by_dur.get(60 * 60)

    estimates: list[FTPEstimate] = []

    if best_20:
        estimates.append(
            FTPEstimate(
                ftp=round(best_20 * 0.95),
                method="20min_95pct",
                duration_seconds=20 * 60,
                raw_power=best_20,
            )
        )

    if best_60:
        estimates.append(
            FTPEstimate(
                ftp=round(best_60),
                method="60min_best",
                duration_seconds=60 * 60,
                raw_power=best_60,
            )
        )

    if not estimates:
        return None

    return min(estimates, key=lambda e: e.ftp)


def build_power_profile(
    activity_inputs: list[ActivityCurveInput],
) -> PowerProfile:
    """
    Build a complete power profile from multiple activities.

    Merges all per-activity curves into a best-of curve, estimates FTP
    from the merged curve, and packages everything for display.
    """
    if not activity_inputs:
        return PowerProfile(
            curve=[],
            ftp_estimate=None,
            activity_count=0,
            date_range=(datetime.date.today(), datetime.date.today()),
            activity_curves=[],
        )

    merged = merge_power_curves(activity_inputs)
    ftp_est = estimate_ftp_from_curve(merged)

    dates = [inp.date for inp in activity_inputs]
    return PowerProfile(
        curve=merged,
        ftp_estimate=ftp_est,
        activity_count=len(activity_inputs),
        date_range=(min(dates), max(dates)),
        activity_curves=activity_inputs,
    )
