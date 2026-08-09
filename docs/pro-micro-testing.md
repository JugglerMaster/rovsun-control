# Pro Micro bench setup (A5 protocol RX / TX testing)

The **Arduino Pro Micro (ATmega32U4, 5 V)** is the safe, 5 V-tolerant stand-in
used during reverse-engineering and for validating the ESPHome firmware without
risking the live mini-split. The A5 bus is **5 V** on both signal lines, so the
Pro Micro (5 V logic) can sit on it directly, while the XIAO C3 (3.3 V) must
always go through a level shifter.

Two sketches live under `sniff/`:

| Sketch | Role | Direction |
|--------|------|-----------|
| `rovsun-promicro-tx/rovsun-promicro-tx.ino` | Passive A5 frame monitor **plus** a guarded sender you trigger over USB | **RX** (monitor) and **TX** (sender) |
| `rovsun-leonardo-sniff/rovsun-leonardo-sniff.ino` | Receive-only byte tap; echoes raw bytes to USB unchanged | **RX** only |

## Flashing

Use Arduino CLI (the board is an **Arduino Leonardo** core):

```powershell
arduino-cli compile -b arduino:avr:leonardo -p COM10 --upload sniff/rovsun-promicro-tx/rovsun-promicro-tx.ino
```

- The 32U4 bootloader drops in on a **DTR/RTS reset** — the uploader toggles it
  automatically, so a manual reset is normally not needed. If a normal upload
  fails, tap RESET during the "Uploading" phase.
- Opening the USB CDC port also asserts DTR and **reboots the sketch**, reprinting
  its banner (`Rovsun A5 monitor ready...`). Wait ~2 s after opening a port
  before sending commands.

## Identifying the port

- Arduino-branded / Leo-compatible: **VID `0x2341`**, PID `0x8036` (CDC) or
  `0x0036` (bootloader).
- SparkFun Pro Micro clone: VID `0x9025`.
- In testing it enumerated as **COM8 / COM10** (the number changes after each
  DTR reset). Confirm with `Get-PnpDevice -Class Ports` before relying on a port.

## Baud / framing

- USB console: **115200** (human-readable framed output).
- `Serial1` (the A5 bus): **115200 8N1**. RX1 = pin **D0**, TX1 = pin **D1**.

## Wiring

### RX tap (listen only — safe against a live bus)

```
Pro Micro D0 (RX1)  <-  signal line you want to watch
Pro Micro GND       --  signal GND
Pro Micro D1 (TX1)  ->  NOT CONNECTED   (never drive the live bus)
Pro Micro 5V        ->  NOT CONNECTED
```

### TX send (bench only — remove the real ESP32 / mini-split from the bus first)

```
Pro Micro D1 (TX1)  ->  device RX
Pro Micro D0 (RX1)  <-  device TX
Pro Micro GND       --  device GND
Pro Micro 5V        ->  NOT CONNECTED (power the bus from its own source)
```

> Rule of thumb: **never** have two TX sources on the bus at once. The guarded
> sender only transmits when you type a command, and only on a bench bus.

## Using it with the XIAO / ESPHome firmware

The ESPHome `rovsun_a5` component (XIAO C3, 3.3 V) is the "module" side. To
bench-test it against the Pro Micro as a fake main board:

1. Flash the Pro Micro with `rovsun-promicro-tx`.
2. Build the level shifter with the **Pro Micro on the HV (5 V) side** and the
   **XIAO on the LV (3.3 V) side**, channels **crossed**:
   - XIAO TX → LV-TX → HV-TX → Pro Micro RX1/D0
   - XIAO RX → LV-RX → HV-RX → Pro Micro TX1/D1
   - Power **HV from 5 V** (the Pro Micro's own 5 V pin or a bench supply).
   - Verify with a meter that the LV side sits at ~3.3 V, never 5 V.
3. From Home Assistant, toggle a control (e.g. Beep). The XIAO transmits an
   `A5 01 01 21 ... 0A 0A` command; the Pro Micro prints it as a `CMD` line with
   `crc=ok` on its USB serial — proof the XIAO TX → shifter → Pro Micro RX path
   works.
4. Watch that output with `tools/promicro-monitor.py`:

   ```powershell
   python tools/promicro-monitor.py --port COM10 --duration 30
   ```

### Current limitation

`rovsun-promicro-tx` is a **passive** monitor + manual sender; it does **not**
auto-ACK or auto-report, so it will not drive Home Assistant state changes on its
own. To validate the reverse path (main board → XIAO → HA), send a report frame
from the Pro Micro, or extend the sketch into a full main-board emulator that
replies to each command with a `0x23` ACK and a `0x21` `0C 0C` report.
