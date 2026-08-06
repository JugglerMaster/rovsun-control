#!/usr/bin/env python3
"""Decode confirmed Rovsun state fields from saved A5 UART captures."""

import argparse
from pathlib import Path


FAN_CODES = {
    0: "auto behavior",
    1: "mute",
    2: "low wind",
    3: "mid-low wind",
    4: "mid wind",
    5: "mid-high wind",
    6: "high wind",
    7: "strong wind",
}
SLEEP_CODES = {0: "off", 1: "standard", 2: "aged", 3: "child"}


def crc16_xmodem(data):
    crc = 0
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def frames(data):
    offset = 0
    while True:
        start = data.find(b"\xa5", offset)
        if start < 0:
            return
        if start + 8 > len(data):
            return
        size = data[start + 7]
        end = start + size
        if size >= 10 and end <= len(data):
            frame = bytes(data[start:end])
            expected = int.from_bytes(frame[8:10], "big")
            if crc16_xmodem(frame[:8] + frame[10:]) == expected:
                yield start, frame
            offset = end
        else:
            offset = start + 1


def find_key(body, key):
    marker = key.to_bytes(2, "big")
    offset = body.find(marker)
    return offset if offset >= 0 else None


def byte_value(body, key):
    offset = find_key(body, key)
    return None if offset is None or offset + 2 >= len(body) else body[offset + 2]


def word_value(body, key):
    offset = find_key(body, key)
    if offset is None or offset + 6 > len(body):
        return None
    return int.from_bytes(body[offset + 2:offset + 6], "big")


def field_text(name, value, labels=None):
    if value is None:
        return None
    label = f" ({labels[value]})" if labels and value in labels else ""
    return f"{name}={value}{label}"


def bounded_field(body, key, maximum):
    value = byte_value(body, key)
    return value if value is not None and value <= maximum else None


def decode(path):
    data = path.read_bytes()
    print(f"{path}: {len(data)} bytes")
    for offset, frame in frames(data):
        if frame[3] != 0x21:
            continue
        body = frame[10:]
        sequence = frame[4] if frame[5] == 0 else frame[5]
        fields = [f"offset={offset}", f"seq=0x{sequence:02X}"]

        temp_c = word_value(body, 0x0002)
        if temp_c is not None:
            fields.append(f"target_c={temp_c / 100:.2f}")
        temp_f = word_value(body, 0x0227)
        if temp_f is not None:
            fields.append(f"target_f={temp_f}")

        fan = bounded_field(body, 0x0005, 7)
        if fan is not None:
            fields.append(field_text("fan", fan, FAN_CODES))
            fan_auto = find_key(body, 0x0005)
            if fan_auto is not None and fan_auto + 5 < len(body):
                fields.append(f"fan_auto_flag={body[fan_auto + 5]}")

        fields.append(field_text("sleep", bounded_field(body, 0x0022, 3), SLEEP_CODES))
        fields.append(field_text("eco", bounded_field(body, 0x0013, 1)))
        fields.append(field_text("beep", bounded_field(body, 0x0025, 1)))
        fields.append(field_text("light", bounded_field(body, 0x001E, 1)))
        fields.append(field_text("generator", bounded_field(body, 0x002D, 3)))
        fields.append(field_text("drying", bounded_field(body, 0x0027, 1)))
        fields.append(field_text("up_down", bounded_field(body, 0x0011, 13)))
        fields.append(field_text("left_right", bounded_field(body, 0x000E, 13)))
        fields = [field for field in fields if field is not None]
        print("  " + " ".join(fields))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="+", type=Path, help="raw .bin capture files")
    args = parser.parse_args()
    for path in args.captures:
        decode(path)


if __name__ == "__main__":
    main()
