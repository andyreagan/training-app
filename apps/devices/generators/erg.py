"""
Generate TrainerRoad / CycleOps ERG (.erg) files from a WorkoutBlock.

ERG format is a simple text file with time-in-minutes and target-watts columns.
Watts here are expressed as % FTP * ftp_watts (defaults to 250 if user has no FTP).
"""


def generate_erg(workout, ftp: int = 250) -> bytes:
    """Return ERG file bytes. ftp is the athlete's FTP in watts."""

    lines = [
        "[COURSE HEADER]",
        f"DESCRIPTION = {workout.description[:120]}",
        f"FILE NAME = {workout.slug}.erg",
        f"MINUTES WATTS",
        "[END COURSE HEADER]",
        "",
        "[COURSE DATA]",
    ]

    current_minute = 0.0

    def watts(pct: int) -> int:
        return round(ftp * pct / 100)

    def emit_segment(start_min: float, duration_sec: int, pct_low: int, pct_high: int) -> float:
        """Emit a segment and return the new current_minute."""
        end_min = start_min + duration_sec / 60
        if pct_low == pct_high:
            lines.append(f"{start_min:.2f}\t{watts(pct_low)}")
            lines.append(f"{end_min:.2f}\t{watts(pct_high)}")
        else:
            # Ramp — two points
            lines.append(f"{start_min:.2f}\t{watts(pct_low)}")
            lines.append(f"{end_min:.2f}\t{watts(pct_high)}")
        return end_min

    for step in workout.structure:
        step_type = step.get("type", "steady")

        if step_type in ("warmup", "cooldown", "ramp", "steady"):
            current_minute = emit_segment(
                current_minute,
                step["duration_seconds"],
                step["power_low"],
                step["power_high"],
            )

        elif step_type == "interval":
            repeat = step.get("repeat", 1)
            for i in range(repeat):
                current_minute = emit_segment(
                    current_minute,
                    step["duration_seconds"],
                    step["power_low"],
                    step["power_high"],
                )
                if i < repeat - 1 or step.get("rest_duration_seconds"):
                    rest_dur = step.get("rest_duration_seconds", 60)
                    current_minute = emit_segment(
                        current_minute,
                        rest_dur,
                        step.get("rest_power_low", 40),
                        step.get("rest_power_high", 55),
                    )

    lines.append("[END COURSE DATA]")
    return "\n".join(lines).encode("utf-8")
