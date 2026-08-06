#!/usr/bin/env python3
"""Inspect saved Rovsun A5 UART streams without opening serial ports."""

import argparse
from pathlib import Path


def frames(data):
    """Split a stream at A5 markers and return offset plus candidate bytes."""
    starts = []
    offset = 0
    while True:
        offset = data.find(b"\xa5", offset)
        if offset < 0:
            break
        starts.append(offset)
        offset += 1

    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(data)
        yield start, bytes(data[start:end])


def sequence(frame):
    if len(frame) < 6:
        return None
    if frame[4] == 0:
        return frame[5]
    if frame[5] == 0:
        return frame[4]
    return None


def describe(frame):
    command = f"0x{frame[3]:02X}" if len(frame) > 3 else "?"
    seq = sequence(frame)
    sequence_text = f"seq=0x{seq:02X}" if seq is not None else "seq=?"
    return f"cmd={command} {sequence_text} len={len(frame)} {frame.hex(' ')}"


def inspect(path):
    data = path.read_bytes()
    print(f"{path}: {len(data)} bytes")
    found = list(frames(data))
    if not found:
        print("  no A5 markers")
        return
    for offset, frame in found:
        print(f"  offset={offset}: {describe(frame)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", nargs="+", type=Path, help="raw .bin capture files")
    args = parser.parse_args()
    for path in args.captures:
        inspect(path)


if __name__ == "__main__":
    main()
