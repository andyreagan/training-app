"""
Unit tests for the power curve and FTP estimation engine.

Pure math — no database, no Django ORM.
"""

import datetime

from apps.fatigue.power import (
    ActivityCurveInput,
    MergedCurvePoint,
    PowerCurvePoint,
    build_power_profile,
    compute_power_curve,
    compute_rolling_average,
    estimate_ftp,
    estimate_ftp_from_curve,
    merge_power_curves,
)

# ── Rolling average ───────────────────────────────────────────────────────────


class TestRollingAverage:
    def test_empty(self):
        assert compute_rolling_average([]) == []

    def test_single_value(self):
        assert compute_rolling_average([200]) == [200.0]

    def test_constant_power(self):
        watts = [200] * 100
        smoothed = compute_rolling_average(watts, window_seconds=30)
        assert all(v == 200.0 for v in smoothed)

    def test_smooths_spike(self):
        # 29 values of 200, then a spike to 500, then 200s
        watts = [200] * 29 + [500] + [200] * 70
        smoothed = compute_rolling_average(watts, window_seconds=30)
        # The spike should be dampened
        assert smoothed[29] < 500
        assert smoothed[29] > 200

    def test_length_preserved(self):
        watts = [150 + i for i in range(60)]
        smoothed = compute_rolling_average(watts, window_seconds=10)
        assert len(smoothed) == len(watts)

    def test_expanding_window_at_start(self):
        watts = [100, 200, 300]
        smoothed = compute_rolling_average(watts, window_seconds=10)
        # First value: just itself
        assert smoothed[0] == 100.0
        # Second value: avg of [100, 200]
        assert smoothed[1] == 150.0
        # Third value: avg of [100, 200, 300]
        assert smoothed[2] == 200.0


# ── Power curve ───────────────────────────────────────────────────────────────


class TestPowerCurve:
    def test_empty(self):
        assert compute_power_curve([]) == []

    def test_constant_power(self):
        watts = [250] * 3600  # 1 hour at 250W
        curve = compute_power_curve(watts)
        # Every duration should be 250W
        for point in curve:
            assert point.watts == 250.0

    def test_best_sprint(self):
        # 10 seconds of 800W, then 3590 seconds of 200W
        watts = [800] * 10 + [200] * 3590
        curve = compute_power_curve(watts)
        # 1-second best should be 800
        one_sec = next(p for p in curve if p.duration_seconds == 1)
        assert one_sec.watts == 800.0
        # 5-second best should be 800 (within the 10s block)
        five_sec = next(p for p in curve if p.duration_seconds == 5)
        assert five_sec.watts == 800.0
        # 1-minute best: best window is [10s×800 + 50s×200] = 300 exactly
        one_min = next(p for p in curve if p.duration_seconds == 60)
        assert one_min.watts == 300.0

    def test_custom_durations(self):
        watts = [300] * 600  # 10 min at 300W
        curve = compute_power_curve(watts, durations=[60, 300, 600])
        assert len(curve) == 3
        assert [p.duration_seconds for p in curve] == [60, 300, 600]
        assert all(p.watts == 300.0 for p in curve)

    def test_skips_durations_longer_than_ride(self):
        watts = [200] * 120  # 2 minutes
        curve = compute_power_curve(watts, durations=[60, 120, 3600])
        assert len(curve) == 2
        durations = [p.duration_seconds for p in curve]
        assert 3600 not in durations

    def test_includes_full_ride_duration(self):
        watts = [250] * 1500  # 25 min
        curve = compute_power_curve(watts)
        durations = [p.duration_seconds for p in curve]
        assert 1500 in durations

    def test_sorted_by_duration(self):
        watts = [200] * 7200
        curve = compute_power_curve(watts)
        durations = [p.duration_seconds for p in curve]
        assert durations == sorted(durations)


# ── FTP estimation ────────────────────────────────────────────────────────────


class TestFTPEstimation:
    def test_too_short_returns_none(self):
        watts = [300] * (19 * 60)  # 19 min — too short
        assert estimate_ftp(watts) is None

    def test_exactly_20_min(self):
        watts = [300] * (20 * 60)
        est = estimate_ftp(watts)
        assert est is not None
        # 95% of 300 = 285
        assert est.ftp == 285
        assert est.method == "20min_95pct"
        assert est.raw_power == 300.0

    def test_with_variable_power(self):
        # 20 min at 280W, rest at 200W
        watts = [280] * (20 * 60) + [200] * (10 * 60)
        est = estimate_ftp(watts)
        assert est is not None
        # Best 20-min is 280, so FTP = 280 * 0.95 = 266
        assert est.ftp == 266
        assert est.method == "20min_95pct"

    def test_60min_ride_uses_more_conservative(self):
        # 20 min at 300W, 40 min at 250W
        watts = [300] * (20 * 60) + [250] * (40 * 60)
        est = estimate_ftp(watts)
        assert est is not None
        # 20-min method: 300 * 0.95 = 285
        # 60-min method: (20*300 + 40*250) / 60 = 267
        # Should pick the lower (more conservative) = 267
        assert est.ftp <= 285
        assert est.method == "60min_best"

    def test_60min_constant_power(self):
        watts = [275] * (60 * 60)
        est = estimate_ftp(watts)
        assert est is not None
        # Both methods give 275 (or 261 for 20-min * 0.95)
        # 60-min best = 275, 20-min * 0.95 = 261
        # More conservative = 261
        assert est.ftp == 261
        assert est.method == "20min_95pct"

    def test_negative_split_ride(self):
        # First half easy, second half hard
        watts = [200] * (30 * 60) + [300] * (30 * 60)
        est = estimate_ftp(watts)
        assert est is not None
        # Best 20-min is in the second half: 300
        # 20-min method: 300 * 0.95 = 285
        assert est.raw_power == 300.0 or est.method == "60min_best"


# ── Multi-activity power curve merging ────────────────────────────────────────


def _d(month, day):
    return datetime.date(2026, month, day)


def _make_curve(watts_by_duration: dict[int, float]) -> list[PowerCurvePoint]:
    return [PowerCurvePoint(d, w) for d, w in sorted(watts_by_duration.items())]


class TestMergePowerCurves:
    def test_empty(self):
        assert merge_power_curves([]) == []

    def test_single_activity(self):
        inp = ActivityCurveInput(
            date=_d(3, 1),
            activity_name="Ride A",
            curve=_make_curve({60: 300.0, 300: 270.0, 1200: 250.0}),
        )
        merged = merge_power_curves([inp])
        assert len(merged) == 3
        assert merged[0].duration_seconds == 60
        assert merged[0].watts == 300.0
        assert merged[0].source_name == "Ride A"

    def test_takes_best_across_activities(self):
        a = ActivityCurveInput(
            date=_d(3, 1),
            activity_name="Sprint Day",
            curve=_make_curve({60: 400.0, 300: 250.0, 1200: 230.0}),
        )
        b = ActivityCurveInput(
            date=_d(3, 5),
            activity_name="Tempo Day",
            curve=_make_curve({60: 280.0, 300: 290.0, 1200: 260.0}),
        )
        merged = merge_power_curves([a, b])

        by_dur = {m.duration_seconds: m for m in merged}
        # 1-min best from Sprint Day
        assert by_dur[60].watts == 400.0
        assert by_dur[60].source_name == "Sprint Day"
        # 5-min best from Tempo Day
        assert by_dur[300].watts == 290.0
        assert by_dur[300].source_name == "Tempo Day"
        # 20-min best from Tempo Day
        assert by_dur[1200].watts == 260.0
        assert by_dur[1200].source_name == "Tempo Day"

    def test_different_durations_union(self):
        """Activities with different available durations should all appear."""
        a = ActivityCurveInput(
            date=_d(3, 1),
            activity_name="Short",
            curve=_make_curve({5: 600.0, 60: 350.0}),
        )
        b = ActivityCurveInput(
            date=_d(3, 5),
            activity_name="Long",
            curve=_make_curve({60: 280.0, 1200: 250.0, 3600: 220.0}),
        )
        merged = merge_power_curves([a, b])
        durations = {m.duration_seconds for m in merged}
        assert durations == {5, 60, 1200, 3600}
        # 60s best should come from Short ride
        m60 = next(m for m in merged if m.duration_seconds == 60)
        assert m60.watts == 350.0
        assert m60.source_name == "Short"

    def test_sorted_by_duration(self):
        a = ActivityCurveInput(
            date=_d(3, 1),
            activity_name="A",
            curve=_make_curve({3600: 200.0, 60: 300.0, 300: 250.0}),
        )
        merged = merge_power_curves([a])
        durations = [m.duration_seconds for m in merged]
        assert durations == sorted(durations)


class TestEstimateFTPFromCurve:
    def test_from_single_activity_curve(self):
        curve = _make_curve({60: 350.0, 300: 300.0, 1200: 280.0})
        est = estimate_ftp_from_curve(curve)
        assert est is not None
        assert est.ftp == round(280.0 * 0.95)  # 266
        assert est.method == "20min_95pct"

    def test_with_60min(self):
        curve = _make_curve({1200: 280.0, 3600: 260.0})
        est = estimate_ftp_from_curve(curve)
        assert est is not None
        # 20min: 280 * 0.95 = 266,  60min: 260
        # More conservative = 260
        assert est.ftp == 260
        assert est.method == "60min_best"

    def test_no_20min_returns_none(self):
        curve = _make_curve({60: 400.0, 300: 350.0})
        est = estimate_ftp_from_curve(curve)
        assert est is None

    def test_from_merged_curve(self):
        merged = [
            MergedCurvePoint(60, 350.0, _d(3, 1), "A"),
            MergedCurvePoint(1200, 280.0, _d(3, 5), "B"),
        ]
        est = estimate_ftp_from_curve(merged)
        assert est is not None
        assert est.ftp == round(280.0 * 0.95)


class TestBuildPowerProfile:
    def test_empty(self):
        profile = build_power_profile([])
        assert profile.activity_count == 0
        assert profile.ftp_estimate is None
        assert profile.curve == []

    def test_single_activity(self):
        inp = ActivityCurveInput(
            date=_d(3, 1),
            activity_name="Ride",
            curve=_make_curve({60: 300.0, 1200: 260.0}),
        )
        profile = build_power_profile([inp])
        assert profile.activity_count == 1
        assert profile.ftp_estimate is not None
        assert profile.ftp_estimate.ftp == round(260 * 0.95)
        assert profile.date_range == (_d(3, 1), _d(3, 1))

    def test_multiple_activities(self):
        a = ActivityCurveInput(
            date=_d(3, 1),
            activity_name="Monday",
            curve=_make_curve({60: 350.0, 1200: 250.0}),
        )
        b = ActivityCurveInput(
            date=_d(3, 10),
            activity_name="Wednesday",
            curve=_make_curve({60: 300.0, 1200: 270.0, 3600: 240.0}),
        )
        profile = build_power_profile([a, b])
        assert profile.activity_count == 2
        assert profile.date_range == (_d(3, 1), _d(3, 10))
        # Best 20-min is 270 from Wednesday
        assert profile.ftp_estimate is not None
        # 20min: 270*0.95=256, 60min: 240 → more conservative = 240
        assert profile.ftp_estimate.ftp == 240
        assert len(profile.activity_curves) == 2

    def test_preserves_activity_curves(self):
        inp = ActivityCurveInput(
            date=_d(3, 1),
            activity_name="Ride",
            curve=_make_curve({60: 300.0}),
            perceived_effort=8,
            tsb=5.0,
        )
        profile = build_power_profile([inp])
        assert profile.activity_curves[0].perceived_effort == 8
        assert profile.activity_curves[0].tsb == 5.0
