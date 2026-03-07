"""
Generate Zwift Workout (.zwo) files from a WorkoutBlock.

ZWO is an XML format consumed by Zwift and many other training apps.
Power values are expressed as fractions of FTP (1.0 = 100% FTP).
"""
from xml.etree import ElementTree as ET
from xml.dom import minidom


def _pct_to_frac(pct: int) -> float:
    return round(pct / 100, 3)


def _add_warmup(parent, step: dict):
    ET.SubElement(
        parent,
        "Warmup",
        Duration=str(step["duration_seconds"]),
        PowerLow=str(_pct_to_frac(step["power_low"])),
        PowerHigh=str(_pct_to_frac(step["power_high"])),
    )


def _add_cooldown(parent, step: dict):
    ET.SubElement(
        parent,
        "Cooldown",
        Duration=str(step["duration_seconds"]),
        PowerLow=str(_pct_to_frac(step["power_high"])),  # reversed: high at start
        PowerHigh=str(_pct_to_frac(step["power_low"])),
    )


def _add_steady(parent, step: dict):
    power = _pct_to_frac((step["power_low"] + step["power_high"]) // 2)
    ET.SubElement(
        parent,
        "SteadyState",
        Duration=str(step["duration_seconds"]),
        Power=str(power),
    )


def _add_intervals(parent, step: dict):
    ET.SubElement(
        parent,
        "IntervalsT",
        Repeat=str(step.get("repeat", 1)),
        OnDuration=str(step["duration_seconds"]),
        OffDuration=str(step.get("rest_duration_seconds", 60)),
        OnPower=str(_pct_to_frac((step["power_low"] + step["power_high"]) // 2)),
        OffPower=str(_pct_to_frac((step.get("rest_power_low", 40) + step.get("rest_power_high", 55)) // 2)),
    )


def generate_zwo(workout, ftp: int = 250) -> bytes:  # noqa: ARG001 – ftp unused (ZWO uses FTP fractions)
    """Return ZWO XML bytes for the given WorkoutBlock."""
    root = ET.Element("workout_file")
    ET.SubElement(root, "author").text = "training.andyreagan.com"
    ET.SubElement(root, "name").text = workout.name
    ET.SubElement(root, "description").text = workout.description
    ET.SubElement(root, "sportType").text = "bike"
    ET.SubElement(root, "tags")

    workout_el = ET.SubElement(root, "workout")

    for step in workout.structure:
        step_type = step.get("type", "steady")
        if step_type == "warmup":
            _add_warmup(workout_el, step)
        elif step_type == "cooldown":
            _add_cooldown(workout_el, step)
        elif step_type == "interval":
            _add_intervals(workout_el, step)
        elif step_type == "ramp":
            _add_warmup(workout_el, step)  # ramps map nicely to warmup element
        else:
            _add_steady(workout_el, step)

    raw = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    # minidom adds an XML declaration — keep it
    return pretty.encode("utf-8")
