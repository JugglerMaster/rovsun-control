#!/usr/bin/env python3
"""Monitor / drive the Rovsun A5 Pro Micro bench tool over its USB CDC port.

The Pro Micro runs one of the sketches under ``sniff/``:
  * rovsun-promicro-tx  - passive A5 frame monitor + guarded sender
  * rovsun-leonardo-sniff - raw byte-per-byte RX tap

Usage:
  # Watch the bus for N seconds (the Pro Micro prints framed lines on USB):
  python promicro-monitor.py --port COM10 --duration 30

  # Drive the Pro Micro's guarded sender (it relays the text over Serial1):
  python promicro-monitor.py --port COM10 --send "SEND BEEP ON" --duration 5

  # After a DTR reset the sketch prints a banner; --wait lets it boot first.
"""
import argparse
import serial
import sys
import time


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", default="COM10")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--duration", type=float, default=20.0)
    p.add_argument("--wait", type=float, default=2.0,
                   help="seconds to wait after opening (bootloader / setup)")
    p.add_argument("--send", default=None,
                   help="text to write to the Pro Micro's USB console")
    args = p.parse_args()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.5)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: cannot open {args.port}: {exc}", file=sys.stderr)
        return 2

    time.sleep(args.wait)
    if args.send is not None:
        ser.write((args.send + "\n").encode())
        print(f"> sent to {args.port}: {args.send!r}")

    print(f"--- monitoring {args.port} for {args.duration:g}s ---")
    t0 = time.time()
    try:
        while time.time() - t0 < args.duration:
            line = ser.readline()
            if not line:
                continue
            try:
                text = line.decode(errors="replace").rstrip("\r\n")
            except Exception:  # noqa: BLE001
                text = repr(line)
            print(text)
    except KeyboardInterrupt:
        print("interrupted")
    finally:
        ser.close()
    print("--- done ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
