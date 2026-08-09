# Agent Notes

## Timing Observation

- The AC beeps almost immediately after a button press.
- The unit then begins applying the requested setting.
- Approximately one second into that application, the app updates its displayed state.

This indicates that command delivery and physical response are faster than app
state confirmation. Reverse-engineering should capture both UART directions
with timestamps and distinguish the command, immediate acknowledgment, delayed
status report, and app polling or push-update delay.

## Capture Retention

- Preserve useful raw UART captures in the repository for future protocol study;
  do not rely only on summarized README findings.
- Keep both UART directions when available, with separate files for each
  direction and the baud rate/framing in the filename.
- Include a short manifest or notes file recording the capture date, wiring,
  adapter/port, power state, exact app or remote action, and timestamps.
- Inspect captures before committing and remove or redact Wi-Fi credentials,
  local keys, MAC addresses, IP addresses, and other private metadata.
- Keep original packet bytes unchanged after sanitization; perform decoding on
  copies or through read-only tools.
- Use Git LFS when raw captures are too large for ordinary Git storage.
- Update the README with confirmed findings, but retain the corresponding raw
  capture so mappings and startup behavior remain reproducible.

## Tooling / Flashing

- **Arduino CLI** is installed on this machine and is used to flash the Pro Micro
  sniffer sketches (`sniff/rovsun-promicro-tx/rovsun-promicro-tx.ino`). The Pro
  Micro enumerates as **Arduino Leonardo (ATmega32U4)** on **COM10**; compile and
  upload with:
  `arduino-cli compile -b arduino:avr:leonardo -p COM10 --upload <sketch.ino>`
- The 32U4 bootloader is entered via a **DTR reset** — the uploader (avrdude)
  toggles DTR/RTS to drop into the bootloader before flashing, so a manual reset
  is not needed for a normal upload. Host-side reads that want to catch the
  boot-time banner must also toggle DTR (e.g. `ser.dtr=False; sleep; ser.dtr=True`)
  because the sketch only prints its `setup()` banner once after a reset.
- **Python** (used for ESPHome) is at
  `C:\Users\chris\AppData\Local\Python\pythoncore-3.14-64\python.exe`
  (not on PATH as `python3`); invoke ESPHome with that full path, e.g.
  `& "<path>\python.exe" -m esphome ...` or via the bundled `esphome.exe` in
  `Scripts\`. `pyserial` is available there for ad-hoc serial captures.
