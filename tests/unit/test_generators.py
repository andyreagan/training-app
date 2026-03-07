"""
Unit tests for workout file generators (ZWO, ERG, FIT).

Uses a lightweight mock workout so no database is required.
"""

import struct
import types
from xml.etree import ElementTree as ET

import pytest

from apps.devices.generators.erg import generate_erg
from apps.devices.generators.fit import generate_fit
from apps.devices.generators.zwo import generate_zwo
from apps.plans.progressions import compute_structure


def _make_workout(category: str = "vo2max", score: float = 5.0) -> types.SimpleNamespace:
    """Build a minimal workout namespace that the generators expect."""
    structure = compute_structure(category, score)
    return types.SimpleNamespace(
        name="Test VO2max",
        slug="test-vo2max",
        description="A test workout",
        structure=structure,
    )


# ── ZWO ───────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_zwo_returns_bytes():
    data = generate_zwo(_make_workout())
    assert isinstance(data, bytes)


@pytest.mark.unit
def test_zwo_is_valid_xml():
    data = generate_zwo(_make_workout())
    root = ET.fromstring(data.decode("utf-8"))
    assert root.tag == "workout_file"


@pytest.mark.unit
def test_zwo_has_workout_element():
    data = generate_zwo(_make_workout())
    root = ET.fromstring(data.decode("utf-8"))
    assert root.find("workout") is not None


@pytest.mark.unit
def test_zwo_has_warmup_and_cooldown():
    data = generate_zwo(_make_workout())
    root = ET.fromstring(data.decode("utf-8"))
    workout_el = root.find("workout")
    tags = [child.tag for child in workout_el]
    assert "Warmup" in tags
    assert "Cooldown" in tags


@pytest.mark.unit
def test_zwo_interval_zone_has_intervals_element():
    data = generate_zwo(_make_workout("vo2max", 5.0))
    root = ET.fromstring(data.decode("utf-8"))
    workout_el = root.find("workout")
    tags = [child.tag for child in workout_el]
    assert "IntervalsT" in tags


@pytest.mark.unit
def test_zwo_steady_zone_has_steady_state_element():
    data = generate_zwo(_make_workout("endurance", 5.0))
    root = ET.fromstring(data.decode("utf-8"))
    workout_el = root.find("workout")
    tags = [child.tag for child in workout_el]
    assert "SteadyState" in tags


@pytest.mark.unit
def test_zwo_power_values_are_fractions():
    """ZWO power values should be 0.0–2.0 (fractions of FTP, not percentages)."""
    data = generate_zwo(_make_workout())
    root = ET.fromstring(data.decode("utf-8"))
    workout_el = root.find("workout")
    for child in workout_el:
        for attr in ("PowerLow", "PowerHigh", "Power", "OnPower", "OffPower"):
            val = child.get(attr)
            if val is not None:
                assert 0.0 <= float(val) <= 2.5, (
                    f"{child.tag}.{attr}={val} outside expected fraction range"
                )


@pytest.mark.unit
def test_zwo_accepts_ftp_kwarg():
    """Regression: generate_zwo must accept ftp= so views.py can call it uniformly."""
    data = generate_zwo(_make_workout(), ftp=300)
    assert isinstance(data, bytes)


# ── ERG ───────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_erg_returns_bytes():
    data = generate_erg(_make_workout())
    assert isinstance(data, bytes)


@pytest.mark.unit
def test_erg_has_course_header_section():
    text = generate_erg(_make_workout()).decode("utf-8")
    assert "[COURSE HEADER]" in text
    assert "[END COURSE HEADER]" in text


@pytest.mark.unit
def test_erg_has_course_data_section():
    text = generate_erg(_make_workout()).decode("utf-8")
    assert "[COURSE DATA]" in text
    assert "[END COURSE DATA]" in text


@pytest.mark.unit
def test_erg_data_rows_are_time_watts():
    text = generate_erg(_make_workout()).decode("utf-8")
    in_data = False
    for line in text.splitlines():
        if line == "[COURSE DATA]":
            in_data = True
            continue
        if line == "[END COURSE DATA]":
            break
        if in_data and line.strip():
            parts = line.split("\t")
            assert len(parts) == 2, f"Expected 2 tab-separated columns, got: {line!r}"
            float(parts[0])  # time in minutes — must be numeric
            int(parts[1])    # watts — must be integer


@pytest.mark.unit
def test_erg_time_is_monotonically_increasing():
    text = generate_erg(_make_workout()).decode("utf-8")
    times = []
    in_data = False
    for line in text.splitlines():
        if line == "[COURSE DATA]":
            in_data = True
            continue
        if line == "[END COURSE DATA]":
            break
        if in_data and line.strip():
            times.append(float(line.split("\t")[0]))
    # Times should be non-decreasing
    assert times == sorted(times)


@pytest.mark.unit
def test_erg_watts_are_positive():
    text = generate_erg(_make_workout(), ftp=250).decode("utf-8")
    in_data = False
    for line in text.splitlines():
        if line == "[COURSE DATA]":
            in_data = True
            continue
        if line == "[END COURSE DATA]":
            break
        if in_data and line.strip():
            watts = int(line.split("\t")[1])
            assert watts > 0


@pytest.mark.unit
def test_erg_ftp_scales_watts():
    """Higher FTP → proportionally higher watts."""
    w250 = generate_erg(_make_workout(), ftp=250).decode("utf-8")
    w300 = generate_erg(_make_workout(), ftp=300).decode("utf-8")

    def max_watts(text):
        in_data = False
        peak = 0
        for line in text.splitlines():
            if "[COURSE DATA]" in line:
                in_data = True
                continue
            if "[END COURSE DATA]" in line:
                break
            if in_data and line.strip():
                peak = max(peak, int(line.split("\t")[1]))
        return peak

    assert max_watts(w300) > max_watts(w250)


# ── FIT ───────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_fit_returns_bytes():
    data = generate_fit(_make_workout())
    assert isinstance(data, bytes)


@pytest.mark.unit
def test_fit_has_correct_magic_bytes():
    """FIT files must contain the magic string '.FIT' at bytes 8–12 of the header."""
    data = generate_fit(_make_workout())
    assert data[8:12] == b".FIT"


@pytest.mark.unit
def test_fit_header_size_byte():
    """Byte 0 of a FIT file is the header size (must be 14)."""
    data = generate_fit(_make_workout())
    assert data[0] == 14


@pytest.mark.unit
def test_fit_minimum_size():
    """Even the simplest workout produces a meaningful file."""
    data = generate_fit(_make_workout())
    assert len(data) >= 100


@pytest.mark.unit
def test_fit_data_size_consistent():
    """data_size in header (bytes 4–8) must match actual data length."""
    data = generate_fit(_make_workout())
    declared = struct.unpack_from("<I", data, 4)[0]
    # Body = total - 14 (header) - 2 (file CRC)
    actual = len(data) - 14 - 2
    assert declared == actual


@pytest.mark.unit
def test_fit_ftp_scales_power():
    """Generating at different FTPs should produce different file content."""
    d250 = generate_fit(_make_workout(), ftp=250)
    d300 = generate_fit(_make_workout(), ftp=300)
    assert d250 != d300
