#!/usr/bin/env python3
"""Capture Rovsun A5 frames from the Pro Mini AC-emulator / capture bridge.

The Pro Mini (sniff/rovsun-promini-ac) forwards every byte it receives from the
Tuya module as a "[RX] <hex...>" line on its USB/FTDI console, and logs its own
AC responses as "[TX] <hex...>" lines. This tool:

  * opens the Pro Mini's FTDI port (115200 8N1) and toggles DTR so the boot
    banner is captured,
  * prints each line with a timestamp,
  * appends the full console transcript to a .log file under --outdir,
  * extracts the raw module->AC bytes (the "[RX]" frames, in order) into a
    sidecar ".bin" you can feed to tools/a5-stream-inspector.py / the decoders.

Usage:
  python pro-mini-capture.py --port COM10 --duration 60
  python pro-mini-capture.py --port COM10 --duration 120 --outdir captures/mymod
"""
import argparse
import serial
import sys
import time
from pathlib import Path


def parse_hex(line):
    tag = "[RX] "
    idx = line.find(tag)
    if idx < 0:
        return None
    tokens = line[idx + len(tag):].split()
    try:
        return bytes(int(t, 16) for t in tokens)
    except ValueError:
        return None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", default="COM10")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--duration", type=float, default=30.0)
    p.add_argument("--wait", type=float, default=2.0,
                   help="seconds to wait after opening (bootloader / setup)")
    p.add_argument("--outdir", default="captures/promini")
    args = p.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log_path = outdir / f"{args.port}_{args.baud}_8N1_{stamp}.log"
    bin_path = outdir / f"{args.port}_{args.baud}_8N1_{stamp}_module_to_ac.bin"

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.5)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: cannot open {args.port}: {exc}", file=sys.stderr)
        return 2

    # Toggle DTR to catch the sketch's setup() banner after a reset.
    try:
        ser.dtr = False
        time.sleep(0.2)
        ser.dtr = True
    except Exception:  # noqa: BLE001
        pass

    time.sleep(args.wait)

    log_f = log_path.open("w", encoding="utf-8")
    bin_f = bin_path.open("wb")
    print(f"--- logging to {log_path}")
    print(f"--- raw module->AC bytes -> {bin_path}")
    print(f"--- monitoring {args.port} for {args.duration:g}s ---")

    t0 = time.time()
    raw_count = 0
    try:
        while time.time() - t0 < args.duration:
            raw = ser.readline()
            if not raw:
                continue
            text = raw.decode(errors="replace").rstrip("\r\n")
            ts = time.strftime("%H:%M:%S")
            out = f"{ts} {text}"
            print(out)
            log_f.write(out + "\n")
            log_f.flush()
            if text.startswith("[RX]"):
                data = parse_hex(text)
                if data:
                    bin_f.write(data)
                    bin_f.flush()
                    raw_count += len(data)
    except KeyboardInterrupt:
        print("interrupted")
    finally:
        ser.close()
        log_f.close()
        bin_f.close()
    print(f"--- done. {raw_count} raw module->AC bytes saved to {bin_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
