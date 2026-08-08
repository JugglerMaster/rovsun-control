#!/usr/bin/env python3
"""Build, but never transmit, a Rovsun command from a captured template."""

import argparse
from pathlib import Path


def crc16_xmodem(data):
    crc = 0
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def command_frames(data):
    offset = 0
    while True:
        start = data.find(b"\xa5", offset)
        if start < 0:
            return
        if start + 8 > len(data):
            return
        size = data[start + 7]
        end = start + size
        if size >= 12 and end <= len(data):
            frame = bytearray(data[start:end])
            expected = int.from_bytes(frame[8:10], "big")
            if (frame[3] == 0x21 and frame[10:12] == b"\x0a\x0a"
                    and crc16_xmodem(frame[:8] + frame[10:]) == expected):
                yield start, frame
            offset = end
        else:
            offset = start + 1


def parse_replacement(value):
    try:
        key, raw = value.split("=", 1)
        key_value = int(key, 0)
        replacement = bytes.fromhex(raw.replace(" ", ""))
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("use KEY=HEXBYTES, for example 0x0227=0000004B") from exc
    if not 0 <= key_value <= 0xFFFF or not replacement:
        raise argparse.ArgumentTypeError("key must be 16-bit and replacement cannot be empty")
    return key_value.to_bytes(2, "big"), replacement


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path, help="raw capture containing a command template")
    parser.add_argument("--replace", type=parse_replacement,
                        help="replace one same-length field, such as 0x0227=0000004B")
    parser.add_argument("--sequence", type=lambda value: int(value, 0), default=None,
                        help="set the command sequence byte, 0-255")
    parser.add_argument("--output", type=Path, help="optional output file for built bytes")
    args = parser.parse_args()
    if args.sequence is not None and not 0 <= args.sequence <= 0xFF:
        parser.error("--sequence must be between 0 and 255")

    matches = list(command_frames(args.capture.read_bytes()))
    if not matches:
        parser.error("no CRC-valid 0A 0A command frame found")
    _, frame = matches[0]

    if args.replace:
        key, replacement = args.replace
        position = frame.find(key, 12)
        if position < 0:
            parser.error(f"field {key.hex()} not found in command template")
        value_start = position + 2
        value_end = value_start + len(replacement)
        if value_end > len(frame):
            parser.error("replacement extends beyond command frame")
        frame[value_start:value_end] = replacement

    if args.sequence is not None:
        frame[4] = args.sequence

    frame[8:10] = crc16_xmodem(frame[:8] + frame[10:]).to_bytes(2, "big")
    result = bytes(frame)
    print(result.hex(" "))
    if args.output:
        args.output.write_bytes(result)


if __name__ == "__main__":
    main()
