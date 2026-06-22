"""
Heart rate analysis engine.

Pure Python — no Django imports.  Provides:

  1. hrTSS — Training Stress Score estimated from heart rate when no power
     data is available.  Uses Coggan's TRIMP-based formula scaled to match
     power-based TSS.

  2. Effort estimation from HR — maps average HR as a fraction of max HR
     to a 1–10 perceived effort scale.

  3. HR-adjusted FTP estimation — when paired power+HR data exist, uses
     HR to assess how hard the rider was working and scales the FTP
     estimate accordingly.  A submaximal ride (low HR fraction) implies
     true FTP is higher than the raw power numbers suggest.

Reference
─────────
Coggan, A. (2003).  Training and racing with a power meter.

The hrTSS formula:
    hr_fraction = (avg_hr - resting_hr) / (max_hr - resting_hr)
    hrTSS = (duration_hours) × hr_fraction × 100 × k
    where k is an exponential scaling factor that makes the TSS numbers
    approximate power-based TSS for typical cycling efforts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

DEFAULT_RESTING_HR = 60


@dataclass
class HrTSSResult:
    """HR-based Training Stress Score."""

    hr_tss: float
    avg_hr: float
    hr_fraction: float  # fraction of HR reserve used (0.0–1.0)
    method: str  # "trimp" or "simple"


@dataclass
class HrEffortEstimate:
    """Effort estimated from heart rate data."""

    effort: int  # 1–10
    hr_fraction: float
    avg_hr: float
    label: str


@dataclass
class HrAdjustedFTP:
    """FTP estimate adjusted for submaximal effort based on HR."""

    ftp_raw: int  # FTP from power alone (95% of best 20min)
    ftp_adjusted: int  # FTP scaled up for submaximal effort
    hr_fraction: float  # how hard they were working (0–1)
    confidence: str  # "high", "medium", "low"
    method: str


# ── hrTSS ─────────────────────────────────────────────────────────────────────


def compute_hr_tss(
    avg_hr: float,
    max_hr: int,
    duration_seconds: int,
    resting_hr: int = DEFAULT_RESTING_HR,
) -> HrTSSResult | None:
    """
    Compute HR-based TSS from average HR.

    Uses the exponential TRIMP formula scaled to approximate power-based
    TSS.  Returns None if inputs are invalid.

    Parameters
    ----------
    avg_hr
        Average heart rate during the activity.
    max_hr
        Athlete's maximum heart rate.
    duration_seconds
        Duration of the activity.
    resting_hr
        Athlete's resting heart rate (default 60 bpm).
    """
    if not avg_hr or not max_hr or max_hr <= resting_hr or avg_hr < resting_hr:
        return None

    hr_reserve = max_hr - resting_hr
    hr_fraction = (avg_hr - resting_hr) / hr_reserve
    hr_fraction = max(0.0, min(1.0, hr_fraction))

    duration_hours = duration_seconds / 3600.0

    # TRIMP-based formula scaled to approximate power-based TSS.
    # At threshold (~90% HRR), a 1-hour ride should produce ~100 TSS.
    # k = e^(1.92 × hr_fraction) is the exponential heart rate scaling.
    k = math.exp(1.92 * hr_fraction)
    # Normalization constant: at hr_fraction=0.90, k=e^1.728≈5.63
    # We want: 1.0 hours × 0.90 × 5.63 × C ≈ 100 → C ≈ 19.7
    hr_tss = duration_hours * hr_fraction * k * 19.7

    return HrTSSResult(
        hr_tss=round(hr_tss, 1),
        avg_hr=avg_hr,
        hr_fraction=round(hr_fraction, 3),
        method="trimp",
    )


def compute_hr_tss_from_stream(
    hr_data: list[int | float],
    max_hr: int,
    resting_hr: int = DEFAULT_RESTING_HR,
    sample_rate: int = 1,
) -> HrTSSResult | None:
    """
    Compute HR-based TSS from a second-by-second HR stream.

    More accurate than the average-HR method because it weights each
    second by its individual HR fraction.
    """
    if not hr_data or not max_hr or max_hr <= resting_hr:
        return None

    hr_reserve = max_hr - resting_hr
    total_weighted = 0.0
    valid_samples = 0

    for hr in hr_data:
        if hr <= 0:
            continue
        frac = max(0.0, min(1.0, (hr - resting_hr) / hr_reserve))
        k = math.exp(1.92 * frac)
        total_weighted += frac * k
        valid_samples += 1

    if valid_samples == 0:
        return None

    avg_hr = sum(h for h in hr_data if h > 0) / valid_samples
    avg_frac = (avg_hr - resting_hr) / hr_reserve

    # Each sample covers 1/(sample_rate × 3600) hours.
    # hrTSS = sum(frac_i × k_i) × 19.7 / (sample_rate × 3600)
    hr_tss = total_weighted * 19.7 / (sample_rate * 3600)

    return HrTSSResult(
        hr_tss=round(hr_tss, 1),
        avg_hr=round(avg_hr, 1),
        hr_fraction=round(max(0.0, min(1.0, avg_frac)), 3),
        method="trimp",
    )


# ── Effort estimation from HR ────────────────────────────────────────────────


EFFORT_LABELS = {
    1: "Very easy",
    2: "Easy",
    3: "Light",
    4: "Moderate",
    5: "Somewhat hard",
    6: "Hard",
    7: "Very hard",
    8: "Extremely hard",
    9: "Near maximal",
    10: "Maximal",
}

# Mapping from HR fraction (of reserve) to RPE 1–10.
# Based on Borg's CR-10 scale correlation with %HRR.
_HR_EFFORT_BREAKPOINTS = [
    (0.00, 1),
    (0.30, 2),
    (0.40, 3),
    (0.50, 4),
    (0.60, 5),
    (0.70, 6),
    (0.80, 7),
    (0.87, 8),
    (0.93, 9),
    (0.97, 10),
]


def estimate_effort_from_hr(
    avg_hr: float,
    max_hr: int,
    resting_hr: int = DEFAULT_RESTING_HR,
) -> HrEffortEstimate | None:
    """
    Estimate perceived effort (1–10) from average heart rate.

    Uses the fraction of heart rate reserve (Karvonen method) mapped
    to a 1–10 RPE scale via standard breakpoints.

    Returns None if inputs are invalid.
    """
    if not avg_hr or not max_hr or max_hr <= resting_hr:
        return None

    hr_reserve = max_hr - resting_hr
    hr_fraction = (avg_hr - resting_hr) / hr_reserve
    hr_fraction = max(0.0, min(1.0, hr_fraction))

    effort = 1
    for threshold, level in _HR_EFFORT_BREAKPOINTS:
        if hr_fraction >= threshold:
            effort = level

    return HrEffortEstimate(
        effort=effort,
        hr_fraction=round(hr_fraction, 3),
        avg_hr=avg_hr,
        label=EFFORT_LABELS[effort],
    )


# ── HR-adjusted FTP estimation ───────────────────────────────────────────────


def adjust_ftp_for_hr(
    ftp_raw: int,
    avg_hr: float,
    max_hr: int,
    resting_hr: int = DEFAULT_RESTING_HR,
) -> HrAdjustedFTP | None:
    """
    Adjust an FTP estimate based on how hard the rider was working.

    If the rider held a given power at only 80% of their HR reserve,
    they weren't at maximal effort — true FTP is likely higher.

    The adjustment scales up the raw FTP by the inverse of the HR
    fraction, capped at a reasonable maximum (1.15x).

    Confidence levels:
      high   — HR fraction ≥ 0.90 (near all-out, minimal adjustment needed)
      medium — HR fraction 0.75–0.90 (moderate adjustment)
      low    — HR fraction < 0.75 (large adjustment, less reliable)

    Returns None if inputs are invalid.
    """
    if not ftp_raw or not avg_hr or not max_hr or max_hr <= resting_hr:
        return None

    hr_reserve = max_hr - resting_hr
    hr_fraction = (avg_hr - resting_hr) / hr_reserve
    hr_fraction = max(0.0, min(1.0, hr_fraction))

    if hr_fraction < 0.50:
        # Too easy to meaningfully estimate FTP
        return None

    # Scale factor: at hr_fraction=1.0, scale=1.0 (no adjustment).
    # At hr_fraction=0.80, scale ≈ 1.08 (adjust up ~8%).
    # At hr_fraction=0.70, scale ≈ 1.12.
    # Capped at 1.15 to avoid wild overestimates.
    if hr_fraction >= 0.95:
        scale = 1.0
    else:
        # Gentle exponential scaling
        scale = min(1.15, 1.0 / (0.3 + 0.7 * hr_fraction))

    ftp_adjusted = round(ftp_raw * scale)

    if hr_fraction >= 0.90:
        confidence = "high"
    elif hr_fraction >= 0.75:
        confidence = "medium"
    else:
        confidence = "low"

    return HrAdjustedFTP(
        ftp_raw=ftp_raw,
        ftp_adjusted=ftp_adjusted,
        hr_fraction=round(hr_fraction, 3),
        confidence=confidence,
        method="hr_adjusted",
    )
