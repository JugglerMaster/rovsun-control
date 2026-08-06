#!/usr/bin/env python3
"""Inspect saved Rovsun A5 UART streams without opening serial ports."""

import argparse
from pathlib import Path


def frames(data):
    """Return A5 frames using byte 7 as the declared total frame length."""
    offset = 0
    while True:
        start = data.find(b"\xa5", offset)
        if start < 0:
            return
        if len(data) - start < 8:
            yield start, bytes(data[start:]), False
            return

        declared_length = data[start + 7]
        end = start + declared_length
        if declared_length >= 8 and end <= len(data):
            yield start, bytes(data[start:end]), True
            offset = end
            continue

        next_start = data.find(b"\xa5", start + 1)
        end = len(data) if next_start < 0 else next_start
        yield start, bytes(data[start:end]), False
        offset = end


def sequence(frame):
    if len(frame) < 6:
        return None
    if frame[4] == 0:
        return frame[5]
    if frame[5] == 0:
        return frame[4]
    return None


def crc16_xmodem(data):
    crc = 0
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def checksum_status(frame):
    if len(frame) < 10:
        return "crc=?"
    expected = int.from_bytes(frame[8:10], "big")
    actual = crc16_xmodem(frame[:8] + frame[10:])
    return f"crc={'ok' if expected == actual else 'BAD'}"


def describe(frame):
    command = f"0x{frame[3]:02X}" if len(frame) > 3 else "?"
    seq = sequence(frame)
    sequence_text = f"seq=0x{seq:02X}" if seq is not None else "seq=?"
    declared = frame[7] if len(frame) > 7 else None
    declared_text = f"declared={declared}" if declared is not None else "declared=?"
    return f"cmd={command} {sequence_text} len={len(frame)} {declared_text} {checksum_status(frame)} {frame.hex(' ')}"


def inspect(path):
    data = path.read_bytes()
    print(f"{path}: {len(data)} bytes")
    found = list(frames(data))
    if not found:
        print("  no A5 markers")
        return
    for offset, frame, complete in found:
        status = "complete" if complete else "incomplete/candidate"
        print(f"  offset={offset} ({status}): {describe(frame)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="+", type=Path, help="raw .bin capture files")
    args = parser.parse_args()
    for path in args.captures:
        inspect(path)


if __name__ == "__main__":
    main()
