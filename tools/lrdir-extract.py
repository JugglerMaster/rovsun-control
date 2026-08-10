#!/usr/bin/env python3
"""List distinct values seen for the louver registers across A5 captures.

Use this after a Pro Mini capture to read off the horizontal/vertical swing
codes the Tuya module emitted. Scans every valid frame in the given file(s)
(raw .bin preferred; .log works too) and reports, per register, the distinct
values with an example frame for each.

Usage:
  python lrdir-extract.py captures/promini/NAME_module_to_ac.bin
  python lrdir-extract.py captures/promini/*.bin
"""
import argparse
import glob
import os
from pathlib import Path


def crc(data):
    c = 0
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) & 0xFFFF if c & 0x8000 else (c << 1) & 0xFFFF
    return c


def frames(data):
    off = 0
    while True:
        i = data.find(b"\xa5", off)
        if i < 0:
            return
        if i + 8 > len(data):
            return
        ln = data[i + 7]
        if ln >= 10 and i + ln <= len(data):
            fr = data[i:i + ln]
            if crc(fr[:8] + fr[10:]) == ((fr[8] << 8) | fr[9]):
                yield fr
            off = i + ln
        else:
            off = i + 1


def extract(data, reg):
    out = {}
    for fr in frames(data):
        body = fr[10:]
        i = 0
        while i + 3 <= len(body):
            if body[i] == (reg >> 8) & 0xFF and body[i + 1] == reg & 0xFF:
                v = body[i + 2]
                if v not in out:
                    out[v] = fr.hex(" ")
            i += 1
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("files", nargs="+", help="capture .bin or .log files (glob ok)")
    args = p.parse_args()

    paths = []
    for pat in args.files:
        paths.extend(glob.glob(pat))
        if not glob.glob(pat):
            paths.append(pat)

    for reg, label in ((0x000E, "horizontal (0x000E)"), (0x0011, "vertical (0x0011)")):
        merged = {}
        for path in paths:
            try:
                data = Path(path).read_bytes()
            except Exception as exc:  # noqa: BLE001
                print(f"skip {path}: {exc}")
                continue
            for v, example in extract(data, reg).items():
                merged.setdefault(v, example)
        if merged:
            print(f"\n{label}: {len(merged)} distinct value(s)")
            for v in sorted(merged):
                print(f"  0x{v:02X}  example: {merged[v]}")
        else:
            print(f"\n{label}: no values found")


if __name__ == "__main__":
    raise SystemExit(main())
