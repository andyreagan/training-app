"""
Unit tests for the Banister impulse-response model.

Pure math — no database, no Django ORM.
"""

import datetime

from apps.fatigue.banister import (
    TSSInput,
    compute,
    tsb_color,
    tsb_zone,
)

# ── Helpers ────────────────────────────────────────────────────────────────────


def d(month, day, year=2026):
    return datetime.date(year, month, day)


def make_inputs(tss_by_date: dict[datetime.date, float], source="actual") -> list[TSSInput]:
    return [TSSInput(date=dt, tss=tss, source=source) for dt, tss in tss_by_date.items()]


# ── Empty / trivial ────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_input(self):
        assert compute([]) == []

    def test_single_day(self):
        result = compute([TSSInput(d(1, 1), 100.0)])
        assert len(result) == 1
        m = result[0]
        assert m.date == d(1, 1)
        assert m.tss == 100.0
        assert m.source == "actual"
        # CTL = 0 * decay + 100 * (1/42) ≈ 2.38
        assert abs(m.ctl - 100 / 42) < 0.1
        # ATL = 0 * decay + 100 * (1/7) ≈ 14.29
        assert abs(m.atl - 100 / 7) < 0.1
        # TSB = CTL - ATL ≈ -11.9
        assert m.tsb < 0

    def test_single_day_rest(self):
        result = compute([TSSInput(d(1, 1), 0.0, source="rest")])
        assert len(result) == 1
        assert result[0].ctl == 0.0
        assert result[0].atl == 0.0
        assert result[0].tsb == 0.0


# ── Gap filling ────────────────────────────────────────────────────────────────


class TestGapFilling:
    def test_fills_gaps_with_rest(self):
        inputs = [
            TSSInput(d(1, 1), 100.0),
            TSSInput(d(1, 5), 80.0),
        ]
        result = compute(inputs)
        assert len(result) == 5  # Jan 1–5 inclusive
        assert result[0].source == "actual"
        assert result[1].source == "rest"
        assert result[2].source == "rest"
        assert result[3].source == "rest"
        assert result[4].source == "actual"

    def test_rest_days_decay_fitness(self):
        inputs = [
            TSSInput(d(1, 1), 100.0),
            TSSInput(d(1, 10), 0.0, source="rest"),
        ]
        result = compute(inputs)
        # CTL should decay over the 9 rest days
        assert result[-1].ctl < result[0].ctl

    def test_unsorted_input(self):
        inputs = [
            TSSInput(d(1, 3), 50.0),
            TSSInput(d(1, 1), 100.0),
            TSSInput(d(1, 2), 75.0),
        ]
        result = compute(inputs)
        assert [m.date for m in result] == [d(1, 1), d(1, 2), d(1, 3)]


# ── Duplicate dates ────────────────────────────────────────────────────────────


class TestDuplicateDates:
    def test_same_date_sums_tss(self):
        inputs = [
            TSSInput(d(1, 1), 60.0),
            TSSInput(d(1, 1), 40.0),
        ]
        result = compute(inputs)
        assert len(result) == 1
        assert result[0].tss == 100.0

    def test_actual_beats_planned_source(self):
        inputs = [
            TSSInput(d(1, 1), 60.0, source="planned"),
            TSSInput(d(1, 1), 40.0, source="actual"),
        ]
        result = compute(inputs)
        assert result[0].source == "actual"


# ── Mathematical properties ────────────────────────────────────────────────────


class TestMathProperties:
    def test_constant_tss_converges_to_that_value(self):
        """If you do exactly TSS=100 every day for a long time, CTL → 100."""
        inputs = [TSSInput(d(1, 1) + datetime.timedelta(days=i), 100.0) for i in range(200)]
        result = compute(inputs)
        # After 200 days, CTL should be very close to 100
        assert abs(result[-1].ctl - 100.0) < 1.0
        # ATL should also converge to 100
        assert abs(result[-1].atl - 100.0) < 1.0
        # TSB = CTL - ATL → 0
        assert abs(result[-1].tsb) < 1.0

    def test_atl_responds_faster_than_ctl(self):
        """A single big day should spike ATL much more than CTL."""
        result = compute([TSSInput(d(1, 1), 200.0)])
        assert result[0].atl > result[0].ctl

    def test_rest_after_training_yields_positive_tsb(self):
        """Train hard, then rest — TSB should eventually go positive (supercompensation)."""
        inputs = [TSSInput(d(1, 1) + datetime.timedelta(days=i), 100.0) for i in range(14)]
        # Then 14 days rest
        inputs.append(TSSInput(d(1, 1) + datetime.timedelta(days=28), 0.0, source="rest"))
        result = compute(inputs)
        # By day 28, ATL has decayed faster than CTL, so TSB should be positive
        assert result[-1].tsb > 0

    def test_overreaching_produces_negative_tsb(self):
        """Sustained high training should produce negative TSB (fatigued)."""
        # Start from zero, ramp up quickly
        inputs = [TSSInput(d(1, 1) + datetime.timedelta(days=i), 150.0) for i in range(7)]
        result = compute(inputs)
        # After a hard week from zero, TSB should be deeply negative
        assert result[-1].tsb < -10

    def test_initial_ctl_atl(self):
        """Custom initial CTL/ATL should carry through."""
        result = compute(
            [TSSInput(d(1, 1), 0.0, source="rest")],
            initial_ctl=80.0,
            initial_atl=50.0,
        )
        assert result[0].ctl > 0  # decayed from 80, not zero
        assert result[0].atl > 0  # decayed from 50, not zero
        # TSB should reflect the initial fitness advantage
        assert result[0].tsb > 0


# ── TSB zones ──────────────────────────────────────────────────────────────────


class TestTSBZones:
    def test_fresh(self):
        assert tsb_zone(20.0) == "fresh"
        assert tsb_zone(15.1) == "fresh"

    def test_neutral(self):
        assert tsb_zone(15.0) == "neutral"
        assert tsb_zone(0.0) == "neutral"
        assert tsb_zone(-9.9) == "neutral"

    def test_tired(self):
        assert tsb_zone(-10.0) == "tired"
        assert tsb_zone(-29.9) == "tired"

    def test_danger(self):
        assert tsb_zone(-30.0) == "danger"
        assert tsb_zone(-50.0) == "danger"

    def test_color_returns_hex(self):
        for val in [20, 0, -15, -40]:
            c = tsb_color(float(val))
            assert c.startswith("#")
            assert len(c) == 7
