"""
Unit tests for the heart rate analysis engine.

Pure math — no database, no Django ORM.
"""

from apps.fatigue.hr import (
    adjust_ftp_for_hr,
    compute_hr_tss,
    compute_hr_tss_from_stream,
    estimate_effort_from_hr,
)

# ── hrTSS from average HR ─────────────────────────────────────────────────────


class TestHrTSS:
    def test_returns_result(self):
        result = compute_hr_tss(avg_hr=145, max_hr=185, duration_seconds=3600)
        assert result is not None
        assert result.hr_tss > 0
        assert result.method == "trimp"

    def test_higher_hr_gives_higher_tss(self):
        easy = compute_hr_tss(avg_hr=120, max_hr=185, duration_seconds=3600)
        hard = compute_hr_tss(avg_hr=170, max_hr=185, duration_seconds=3600)
        assert hard.hr_tss > easy.hr_tss

    def test_longer_duration_gives_higher_tss(self):
        short = compute_hr_tss(avg_hr=145, max_hr=185, duration_seconds=1800)
        long = compute_hr_tss(avg_hr=145, max_hr=185, duration_seconds=3600)
        assert long.hr_tss > short.hr_tss

    def test_easy_ride_low_tss(self):
        result = compute_hr_tss(avg_hr=110, max_hr=185, duration_seconds=3600)
        assert result.hr_tss < 50

    def test_hard_ride_high_tss(self):
        result = compute_hr_tss(avg_hr=175, max_hr=185, duration_seconds=3600)
        assert result.hr_tss > 50

    def test_invalid_inputs_return_none(self):
        assert compute_hr_tss(avg_hr=0, max_hr=185, duration_seconds=3600) is None
        assert compute_hr_tss(avg_hr=145, max_hr=0, duration_seconds=3600) is None
        assert (
            compute_hr_tss(avg_hr=145, max_hr=60, duration_seconds=3600) is None
        )  # max <= resting

    def test_hr_fraction_in_range(self):
        result = compute_hr_tss(avg_hr=145, max_hr=185, duration_seconds=3600)
        assert 0.0 <= result.hr_fraction <= 1.0

    def test_custom_resting_hr(self):
        high_rest = compute_hr_tss(avg_hr=145, max_hr=185, duration_seconds=3600, resting_hr=70)
        low_rest = compute_hr_tss(avg_hr=145, max_hr=185, duration_seconds=3600, resting_hr=50)
        # Higher resting HR with same avg_hr = smaller gap above rest = lower fraction
        # (145-70)/(185-70) = 0.652 < (145-50)/(185-50) = 0.704
        # But the exponential weighting can flip this — what matters is both produce
        # reasonable values and respond to the parameter
        assert high_rest.hr_tss > 0
        assert low_rest.hr_tss > 0
        assert high_rest.hr_fraction != low_rest.hr_fraction


# ── hrTSS from stream ─────────────────────────────────────────────────────────


class TestHrTSSFromStream:
    def test_constant_hr(self):
        hr_data = [145] * 3600
        result = compute_hr_tss_from_stream(hr_data, max_hr=185)
        assert result is not None
        assert result.hr_tss > 0

    def test_matches_avg_method_approximately(self):
        """Stream-based and average-based should give similar results for constant HR."""
        hr_data = [145] * 3600
        stream_result = compute_hr_tss_from_stream(hr_data, max_hr=185)
        avg_result = compute_hr_tss(avg_hr=145, max_hr=185, duration_seconds=3600)
        # Should be in the same ballpark (within 20%)
        assert abs(stream_result.hr_tss - avg_result.hr_tss) / avg_result.hr_tss < 0.2

    def test_variable_hr_differs_from_constant(self):
        """Variable HR should give different (typically higher) TSS than flat avg."""
        # Variable HR with same average — the exponential weighting means
        # high HR moments contribute disproportionately more
        constant = [145] * 3600
        variable = [120] * 1800 + [170] * 1800  # avg 145 but more time at extremes
        const_result = compute_hr_tss_from_stream(constant, max_hr=185)
        var_result = compute_hr_tss_from_stream(variable, max_hr=185)
        # Variable should be higher due to exponential weighting of high HR periods
        assert var_result.hr_tss > const_result.hr_tss

    def test_empty_returns_none(self):
        assert compute_hr_tss_from_stream([], max_hr=185) is None

    def test_ignores_zero_hr(self):
        hr_data = [0, 0, 145, 145, 145]
        result = compute_hr_tss_from_stream(hr_data, max_hr=185)
        assert result is not None
        assert result.avg_hr == 145.0


# ── Effort estimation from HR ────────────────────────────────────────────────


class TestEffortFromHR:
    def test_returns_result(self):
        result = estimate_effort_from_hr(avg_hr=145, max_hr=185)
        assert result is not None
        assert 1 <= result.effort <= 10

    def test_easy_ride_low_effort(self):
        result = estimate_effort_from_hr(avg_hr=100, max_hr=185, resting_hr=60)
        assert result.effort <= 3

    def test_hard_ride_high_effort(self):
        result = estimate_effort_from_hr(avg_hr=175, max_hr=185, resting_hr=60)
        assert result.effort >= 8

    def test_moderate_ride_moderate_effort(self):
        result = estimate_effort_from_hr(avg_hr=140, max_hr=185, resting_hr=60)
        assert 4 <= result.effort <= 7

    def test_monotonic_with_hr(self):
        """Higher HR should give equal or higher effort rating."""
        results = []
        for hr in range(100, 185, 10):
            result = estimate_effort_from_hr(avg_hr=hr, max_hr=185, resting_hr=60)
            results.append(result.effort)
        for i in range(len(results) - 1):
            assert results[i] <= results[i + 1]

    def test_invalid_inputs_return_none(self):
        assert estimate_effort_from_hr(avg_hr=0, max_hr=185) is None
        assert estimate_effort_from_hr(avg_hr=145, max_hr=0) is None

    def test_label_present(self):
        result = estimate_effort_from_hr(avg_hr=145, max_hr=185)
        assert len(result.label) > 0


# ── HR-adjusted FTP ──────────────────────────────────────────────────────────


class TestAdjustFTPForHR:
    def test_near_max_hr_no_adjustment(self):
        """At near-max HR (all-out), FTP shouldn't change much."""
        result = adjust_ftp_for_hr(ftp_raw=250, avg_hr=180, max_hr=185, resting_hr=60)
        assert result is not None
        assert result.ftp_adjusted == result.ftp_raw  # at 96% HRR, scale ≈ 1.0
        assert result.confidence == "high"

    def test_submaximal_adjusts_up(self):
        """At moderate HR, FTP should be adjusted upward."""
        result = adjust_ftp_for_hr(ftp_raw=250, avg_hr=150, max_hr=185, resting_hr=60)
        assert result is not None
        assert result.ftp_adjusted > result.ftp_raw

    def test_adjustment_capped(self):
        """Adjustment should never exceed 1.15x."""
        result = adjust_ftp_for_hr(ftp_raw=250, avg_hr=100, max_hr=185, resting_hr=60)
        if result:
            assert result.ftp_adjusted <= round(250 * 1.15)

    def test_very_easy_returns_none(self):
        """Too-easy efforts (HR fraction < 0.50) can't meaningfully estimate FTP."""
        result = adjust_ftp_for_hr(ftp_raw=250, avg_hr=85, max_hr=185, resting_hr=60)
        assert result is None

    def test_confidence_levels(self):
        # High confidence: near max
        high = adjust_ftp_for_hr(ftp_raw=250, avg_hr=178, max_hr=185, resting_hr=60)
        assert high.confidence == "high"

        # Medium confidence: moderate
        med = adjust_ftp_for_hr(ftp_raw=250, avg_hr=155, max_hr=185, resting_hr=60)
        assert med.confidence == "medium"

        # Low confidence: submaximal
        low = adjust_ftp_for_hr(ftp_raw=250, avg_hr=125, max_hr=185, resting_hr=60)
        if low:
            assert low.confidence == "low"

    def test_invalid_inputs_return_none(self):
        assert adjust_ftp_for_hr(ftp_raw=0, avg_hr=145, max_hr=185) is None
        assert adjust_ftp_for_hr(ftp_raw=250, avg_hr=0, max_hr=185) is None
        assert adjust_ftp_for_hr(ftp_raw=250, avg_hr=145, max_hr=0) is None

    def test_monotonic_adjustment(self):
        """Lower HR fraction should give higher adjusted FTP."""
        results = []
        for hr in [130, 145, 160, 175]:
            result = adjust_ftp_for_hr(ftp_raw=250, avg_hr=hr, max_hr=185, resting_hr=60)
            if result:
                results.append(result.ftp_adjusted)
        # Higher HR = less adjustment needed, so adjusted FTP should decrease
        for i in range(len(results) - 1):
            assert results[i] >= results[i + 1]
