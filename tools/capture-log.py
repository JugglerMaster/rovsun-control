#!/usr/bin/env python3
"""Timestamped serial logger for the Pro Micro A5 monitor (or any line printer).

Opens the port, toggles DTR to catch the sketch banner, and writes every line
with a HH:MM:SS timestamp to both stdout and a .log file under --outdir.

Usage:
  python capture-log.py --port COM10 --duration 150 --outdir captures/h-swing
"""
import argparse
import serial
import sys
import time
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", default="COM10")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--duration", type=float, default=120.0)
    p.add_argument("--wait", type=float, default=2.0)
    p.add_argument("--outdir", default="captures")
    args = p.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_path = outdir / f"{args.port}_{args.baud}_8N1_{stamp}.log"

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.5)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: cannot open {args.port}: {exc}", file=sys.stderr)
        return 2
    try:
        ser.dtr = False
        time.sleep(0.2)
        ser.dtr = True
    except Exception:  # noqa: BLE001
        pass
    time.sleep(args.wait)

    log_f = log_path.open("w", encoding="utf-8")
    print(f"--- logging to {log_path}")
    print(f"--- {args.port} for {args.duration:g}s ---")
    t0 = time.time()
    try:
        while time.time() - t0 < args.duration:
            raw = ser.readline()
            if not raw:
                continue
            ts = time.strftime("%H:%M:%S")
            text = raw.decode(errors="replace").rstrip("\r\n")
            out = f"{ts} {text}"
            print(out)
            log_f.write(out + "\n")
            log_f.flush()
    except KeyboardInterrupt:
        print("interrupted")
    finally:
        ser.close()
        log_f.close()
    print(f"--- done. saved {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
