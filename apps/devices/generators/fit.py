"""
Generate Garmin FIT structured workout files (.fit) from a WorkoutBlock.

FIT binary encoding is done from scratch using the ANT/Garmin FIT protocol spec.
This produces a workout-type FIT file readable by Garmin Connect and Garmin devices.

Reference: https://developer.garmin.com/fit/protocol/
"""
import struct
import time


# ── CRC ──────────────────────────────────────────────────────────────────────

CRC_TABLE = [
    0x0000, 0xCC01, 0xD801, 0x1400, 0xF001, 0x3C00, 0x2800, 0xE401,
    0xA001, 0x6C00, 0x7800, 0xB401, 0x5000, 0x9C01, 0x8801, 0x4400,
]


def _crc_byte(crc: int, byte: int) -> int:
    tmp = CRC_TABLE[crc & 0xF]
    crc = (crc >> 4) & 0x0FFF
    crc ^= tmp ^ CRC_TABLE[byte & 0xF]
    tmp = CRC_TABLE[crc & 0xF]
    crc = (crc >> 4) & 0x0FFF
    crc ^= tmp ^ CRC_TABLE[(byte >> 4) & 0xF]
    return crc


def _crc(data: bytes) -> int:
    crc = 0
    for b in data:
        crc = _crc_byte(crc, b)
    return crc


# ── FIT constants ─────────────────────────────────────────────────────────────

GARMIN_EPOCH = 631065600  # seconds between Unix epoch and 1989-12-31

SPORT_CYCLING = 2
SUB_SPORT_VIRTUAL = 58  # virtual cycling / generic

# workout_step duration types
DURATION_TIME = 0          # duration_value = seconds * 1000
DURATION_OPEN = 7          # "lap button press"

# workout_step target types
TARGET_POWER = 7           # power zone
TARGET_POWER_3S = 8        # 3-sec power (we use raw watts range)
TARGET_OPEN = 0

# intensity
INTENSITY_ACTIVE = 0
INTENSITY_REST = 1
INTENSITY_WARMUP = 2
INTENSITY_COOLDOWN = 3


# ── Message builders ──────────────────────────────────────────────────────────

def _definition_message(local_mesg_num: int, global_mesg_num: int, fields: list) -> bytes:
    """Build a FIT definition message."""
    # fields: list of (field_def_num, size, base_type)
    header = 0x40 | (local_mesg_num & 0x0F)
    reserved = 0x00
    architecture = 0  # little-endian
    num_fields = len(fields)
    body = struct.pack("<BBHB", reserved, architecture, global_mesg_num, num_fields)
    for fdn, size, base_type in fields:
        body += struct.pack("BBB", fdn, size, base_type)
    return bytes([header]) + body


def _data_header(local_mesg_num: int) -> int:
    return local_mesg_num & 0x0F


# FIT base types
UINT8  = 0x02
UINT16 = 0x84
UINT32 = 0x86
STRING = 0x07
ENUM   = 0x00
BYTE   = 0x0D


def _fit_string(s: str, length: int) -> bytes:
    """Null-padded fixed-length UTF-8 string."""
    b = s.encode("utf-8")[:length - 1]
    return b + b"\x00" * (length - len(b))


def _garmin_timestamp() -> int:
    return int(time.time()) - GARMIN_EPOCH


# ── High-level message helpers ────────────────────────────────────────────────

NAME_LEN = 16  # bytes for workout / step name fields


def _file_id_definition() -> bytes:
    # global mesg 0 = file_id
    return _definition_message(0, 0, [
        (0, 1, ENUM),   # type
        (1, 2, UINT16), # manufacturer
        (2, 2, UINT16), # product
        (4, 4, UINT32), # time_created
    ])


def _file_id_data() -> bytes:
    header = bytes([_data_header(0)])
    body = struct.pack("<BHHH", 5, 1, 1, 0)  # type=workout(5), mfr=garmin(1), product=1
    ts = struct.pack("<I", _garmin_timestamp())
    return header + body[:5] + ts


def _workout_definition() -> bytes:
    # global mesg 26 = workout
    return _definition_message(1, 26, [
        (4, 1, ENUM),           # sport
        (6, 2, UINT16),         # num_valid_steps
        (8, NAME_LEN, STRING),  # wkt_name
    ])


def _workout_data(name: str, num_steps: int) -> bytes:
    header = bytes([_data_header(1)])
    sport = struct.pack("B", SPORT_CYCLING)
    steps = struct.pack("<H", num_steps)
    wkt_name = _fit_string(name, NAME_LEN)
    return header + sport + steps + wkt_name


def _step_definition() -> bytes:
    # global mesg 27 = workout_step
    return _definition_message(2, 27, [
        (0, 4, UINT32),         # duration_value
        (1, 4, UINT32),         # target_value_low
        (2, 4, UINT32),         # target_value_high
        (3, 1, ENUM),           # intensity
        (4, 1, ENUM),           # duration_type
        (5, 1, ENUM),           # target_type
        (7, NAME_LEN, STRING),  # wkt_step_name
    ])


def _step_data(
    duration_sec: int,
    power_low_pct: int,
    power_high_pct: int,
    intensity: int,
    ftp: int,
    step_name: str = "",
) -> bytes:
    header = bytes([_data_header(2)])
    duration_value = duration_sec * 1000  # milliseconds
    # FIT power target: 1000 + watts (offset encoding)
    watts_low = max(0, round(ftp * power_low_pct / 100))
    watts_high = max(0, round(ftp * power_high_pct / 100))
    target_low = 1000 + watts_low
    target_high = 1000 + watts_high
    target_type = TARGET_POWER_3S

    body = struct.pack(
        "<IIIBBB",
        duration_value,
        target_low,
        target_high,
        intensity,
        DURATION_TIME,
        target_type,
    )
    name_bytes = _fit_string(step_name, NAME_LEN)
    return header + body + name_bytes


# ── Public API ────────────────────────────────────────────────────────────────

def generate_fit(workout, ftp: int = 250) -> bytes:
    """Return FIT binary bytes for the given WorkoutBlock."""

    # 1. Build step list
    raw_steps = []  # list of (duration_sec, power_low, power_high, intensity, label)

    for step in workout.structure:
        stype = step.get("type", "steady")

        if stype == "warmup":
            raw_steps.append((
                step["duration_seconds"],
                step["power_low"], step["power_high"],
                INTENSITY_WARMUP, "Warmup",
            ))
        elif stype == "cooldown":
            raw_steps.append((
                step["duration_seconds"],
                step["power_high"], step["power_low"],  # reversed for cooldown
                INTENSITY_COOLDOWN, "Cooldown",
            ))
        elif stype == "interval":
            repeat = step.get("repeat", 1)
            for i in range(repeat):
                raw_steps.append((
                    step["duration_seconds"],
                    step["power_low"], step["power_high"],
                    INTENSITY_ACTIVE, f"On {i + 1}/{repeat}",
                ))
                if i < repeat - 1 or step.get("rest_duration_seconds"):
                    raw_steps.append((
                        step.get("rest_duration_seconds", 60),
                        step.get("rest_power_low", 40), step.get("rest_power_high", 55),
                        INTENSITY_REST, "Rest",
                    ))
        elif stype == "ramp":
            raw_steps.append((
                step["duration_seconds"],
                step["power_low"], step["power_high"],
                INTENSITY_ACTIVE, "Ramp",
            ))
        else:  # steady
            raw_steps.append((
                step["duration_seconds"],
                step["power_low"], step["power_high"],
                INTENSITY_ACTIVE, "Work",
            ))

    num_steps = len(raw_steps)

    # 2. Assemble message bytes
    messages = b""
    messages += _file_id_definition()
    messages += _file_id_data()
    messages += _workout_definition()
    messages += _workout_data(workout.name[:NAME_LEN - 1], num_steps)
    messages += _step_definition()
    for dur, plo, phi, intensity, label in raw_steps:
        messages += _step_data(dur, plo, phi, intensity, ftp, label)

    # 3. File header (14 bytes)
    data_size = len(messages)
    header = struct.pack(
        "<BBHI4s",
        14,         # header size
        0x10,       # protocol version
        0x07BC,     # profile version 19.84
        data_size,
        b".FIT",
    )
    header_crc = struct.pack("<H", _crc(header))
    header += header_crc  # now 14 bytes

    # Wait — standard 14-byte header includes the CRC in the 14 bytes
    # Layout: size(1) protocol(1) profile(2) data_size(4) ".FIT"(4) crc(2) = 14
    body = header + messages
    file_crc = struct.pack("<H", _crc(messages))
    return body + file_crc
