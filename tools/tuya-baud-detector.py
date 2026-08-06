#!/usr/bin/env python3
"""Passively inspect one or two UART streams without transmitting.

This tool intentionally never writes to the serial ports. Use one port for
each UART direction when possible; ports supplied together are sampled at the
same baud rate and during the same capture window.
"""

import argparse
from pathlib import Path
import re
import time

import serial


DEFAULT_BAUDRATES = (9600, 19200, 38400, 57600, 115200, 14400)
ALL_BAUDRATES = (
    110, 300, 600, 1200, 2400, 4800, 9600, 14400, 19200, 38400,
    57600, 115200, 128000, 230400, 256000, 460800, 576000, 921600,
)
DEFAULT_FRAMINGS = ("8N1",)
ALL_FRAMINGS = ("7N1", "7N2", "7E1", "7E2", "7O1", "7O2",
                "8N1", "8N2", "8E1", "8E2", "8O1", "8O2")


def tuya_frames(data):
    """Return complete, checksum-valid Tuya frames found in *data*."""
    frames = []
    offset = 0
    while True:
        start = data.find(b"\x55\xaa", offset)
        if start < 0 or len(data) - start < 7:
            break
        payload_length = (data[start + 4] << 8) | data[start + 5]
        frame_length = 7 + payload_length
        if payload_length > 4096:
            offset = start + 1
            continue
        if len(data) - start < frame_length:
            break
        frame = data[start:start + frame_length]
        if sum(frame[:-1]) & 0xFF == frame[-1]:
            frames.append(frame)
            offset = start + frame_length
        else:
            offset = start + 1
    return frames


def frame_summary(frame):
    command = frame[3]
    payload_length = (frame[4] << 8) | frame[5]
    return f"cmd=0x{command:02x} len={payload_length} {frame.hex(' ')}"


def a5_candidates(data):
    """Return offsets and short samples for the observed A5 protocol."""
    candidates = []
    offset = 0
    while True:
        offset = data.find(b"\xa5", offset)
        if offset < 0:
            break
        candidates.append((offset, bytes(data[offset:offset + 32])))
        offset += 1
    return candidates


def capture(ports, baudrate, framing, duration, dtr_ports=()):
    """Capture all supplied ports at one baud rate without transmitting."""
    data_bits = int(framing[0])
    parity = {"N": serial.PARITY_NONE, "E": serial.PARITY_EVEN,
              "O": serial.PARITY_ODD}[framing[1]]
    stop_bits = serial.STOPBITS_ONE if framing[2] == "1" else serial.STOPBITS_TWO
    opened = []
    try:
        for port in ports:
            ser = serial.Serial()
            ser.port = port
            ser.baudrate = baudrate
            ser.bytesize = serial.SEVENBITS if data_bits == 7 else serial.EIGHTBITS
            ser.parity = parity
            ser.stopbits = stop_bits
            ser.timeout = 0
            ser.write_timeout = 0
            ser.xonxoff = False
            ser.rtscts = False
            ser.dsrdtr = False
            # Do not assert modem-control outputs on an adapter connected to
            # the target. This is receive-only, but adapters differ at open.
            ser.dtr = port in dtr_ports
            ser.rts = False
            ser.open()
            ser.reset_input_buffer()
            opened.append((port, ser))

        captured = {port: bytearray() for port in ports}
        if dtr_ports:
            # Native-USB Arduino boards reset when DTR is asserted. Allow the
            # sketch to finish setup and the USB endpoint to reconnect.
            time.sleep(6)
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            received = False
            for port, ser in opened:
                chunk = ser.read(ser.in_waiting or 1)
                if chunk:
                    captured[port].extend(chunk)
                    received = True
            if not received:
                time.sleep(0.005)
        return captured
    finally:
        for _, ser in opened:
            ser.close()


def parse_baudrates(value):
    try:
        rates = tuple(int(item) for item in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("baud rates must be comma-separated integers") from exc
    if not rates or any(rate <= 0 for rate in rates):
        raise argparse.ArgumentTypeError("baud rates must be positive")
    return rates


def parse_framings(value):
    framings = tuple(item.upper() for item in value.split(","))
    if not framings or any(not re.fullmatch(r"[78][NEO][12]", item) for item in framings):
        raise argparse.ArgumentTypeError(
            "framings must be comma-separated values such as 8N1,8N2,7E1"
        )
    return framings


def main():
    parser = argparse.ArgumentParser(
        description="Passively inspect one or two receive-only UART streams"
    )
    parser.add_argument("ports", nargs="+", help="one or two receive-only serial ports")
    parser.add_argument(
        "-t", "--duration", type=float, default=5.0,
        help="seconds to capture at each rate (default: 5)",
    )
    parser.add_argument(
        "-a", "--all", action="store_true",
        help="scan the complete baud-rate list instead of the common rates",
    )
    parser.add_argument(
        "-b", "--baudrates", type=parse_baudrates,
        help="comma-separated baud rates to scan (overrides --all)",
    )
    parser.add_argument(
        "-f", "--framings", type=parse_framings,
        help="comma-separated UART framings to scan (default: 8N1)",
    )
    parser.add_argument(
        "--all-framings", action="store_true",
        help="scan 7/8 data bits, none/odd/even parity, and 1/2 stop bits",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="print frame or protocol samples in the results",
    )
    parser.add_argument(
        "--protocol", choices=("tuya", "a5", "raw"), default="tuya",
        help="protocol inspection mode (default: tuya)",
    )
    parser.add_argument(
        "--raw-dir", type=Path,
        help="save each capture as a raw .bin file in this directory",
    )
    parser.add_argument(
        "--dtr-ports",
        help="comma-separated native-USB ports that require DTR (for example COM10)",
    )
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("--duration must be positive")
    if len(args.ports) > 2:
        parser.error("use at most two serial ports")
    if args.raw_dir:
        args.raw_dir.mkdir(parents=True, exist_ok=True)
    dtr_ports = tuple(item.strip() for item in (args.dtr_ports or "").split(",") if item.strip())

    baudrates = args.baudrates or (ALL_BAUDRATES if args.all else DEFAULT_BAUDRATES)
    framings = args.framings or (ALL_FRAMINGS if args.all_framings else DEFAULT_FRAMINGS)
    results = []
    for baudrate in baudrates:
        for framing in framings:
            print(f"Scanning {baudrate} {framing} for {args.duration:g}s...", flush=True)
            try:
                captured = capture(args.ports, baudrate, framing, args.duration, dtr_ports)
            except serial.SerialException as exc:
                parser.error(str(exc))
            for port, data in captured.items():
                if args.raw_dir:
                    filename = f"{port}_{baudrate}_{framing}.bin".replace(":", "_")
                    (args.raw_dir / filename).write_bytes(data)

                if args.protocol == "tuya":
                    findings = tuya_frames(data)
                    score = len(findings)
                    label = "valid frame(s)"
                elif args.protocol == "a5":
                    findings = a5_candidates(data)
                    score = len(findings)
                    label = "A5 candidate(s)"
                else:
                    findings = []
                    score = len(data)
                    label = "byte(s)"

                result = (score, len(data), baudrate, framing, port, findings)
                results.append(result)
                print(f"  {port}: {score} {label}, {len(data)} byte(s)")
                if args.verbose:
                    if args.protocol == "tuya":
                        for frame in findings:
                            print(f"    {frame_summary(frame)}")
                    elif args.protocol == "a5":
                        for offset, sample in findings[:10]:
                            print(f"    offset={offset}: {sample.hex(' ')}")

    print("\nBest candidates:")
    ranked = sorted(results, key=lambda result: (result[0], result[1]), reverse=True)
    for frame_count, byte_count, baudrate, framing, port, _ in ranked[:5]:
        print(f"  {port}: {baudrate} {framing} ({frame_count} score, {byte_count} byte(s))")
    if not ranked or ranked[0][0] == 0:
        if args.protocol == "tuya":
            print("No checksum-valid Tuya frames found. Capture across a power cycle or extend --duration.")
        elif args.protocol == "a5":
            print("No A5 candidates found. Capture across a power cycle or extend --duration.")
        else:
            print("No bytes captured. Check wiring, grounds, and port assignments.")


if __name__ == "__main__":
    main()
