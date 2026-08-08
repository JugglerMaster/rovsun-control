# rovsun-control

Local control of a Rovsun mini-split that ships with a Realtek **RTL8720CF**
Wi-Fi module. The module talks to the main control board over a **custom `A5`
UART protocol** (not the Tuya `55 AA` MCU protocol), running at **115200 8N1**.
The stock module can be replaced by a Seeed XIAO ESP32-C3 running an ESPHome
external component (`esphome/components/rovsun_a5`) that speaks this protocol
directly, removing the cloud/app dependency.

## Status

- **Protocol decoded and confirmed** (2026-08-07): bidirectional `A5 01 01 21`
  command frames and `0x21` state reports, CRC-16/XMODEM over the header + body
  (CRC bytes excluded). Setting commands use an `0A 0A` body prefix; the board
  acknowledges with a `0x23` frame echoing the sequence number and then applies
  the change in a `0x21` report.
- **Working ESPHome firmware** (`esphome/rovsun-c3.yaml` + component): a single
  `climate` entity (power, mode, fan, vertical swing, setpoint) plus switches and
  selects for the remaining confirmed controls. State is published from the
  board's `0x21` reports, so IR-remote changes are observed and reconciled.
- **Restore-on-power-on**: the controller caches every value commanded through
  ESPHome and replays them when it detects a power **off→on** transition (power
  restored, or the IR remote turning the unit on). This re-asserts HA's desired
  fan / swing / beep / light / drying / eco / sleep / generator / left-right /
  mode / setpoint, which the unit otherwise loses (it returns to factory defaults
  on power loss, and IR power-on applies the remote's stored config).

See [Protocol reference](#protocol-reference) for the full confirmed register map.

## Hardware

- Seeed XIAO ESP32-C3 (native USB-C, Wi-Fi, 3.3 V logic) is the preferred
  replacement. Two mini-splits are available; experiment on one, keep the other
  stock.
- The 4-pin JST toward the main board carries **5 V** UART on both signal pins
  (confirmed ~5 V idle). The stock module's breakout up-shifts its TX and
  down-shifts its RX, so to the replacement the wiring is straight-through
  relative to the main board:
  - controller **RX** → main-board **TX** (the line that continuously streams
    `A5 01 01 21` frames)
  - controller **TX** → main-board **RX** (idle until a command is sent)
  - GND common; power the replacement from the board's own 5 V rail, **never**
    connect the board 5 V to a 3.3 V device rail.
- Use a 3.3 V/5 V level shifter between the XIAO and the 5 V signals.

### Wiring (XIAO C3)

| XIAO C3      | Main MCU / module pad |
|--------------|-----------------------|
| D7 GPIO20 (TX1) | main-MCU RX (idle pin) |
| D6 GPIO21 (RX1) | main-MCU TX (streaming pin) |
| GND          | board GND |
| 3V3 / 5V     | module-power rail, only after measuring it |

Flash with `esphome run esphome/rovsun-c3.yaml` (USB-C). Secrets live in
`esphome/secrets.yaml`.

## Protocol reference

Every frame begins `A5 01 01/00 21 <seq> 00 00 <len> <crc16 hi> <crc16 lo>
<0A/0C 0A/0C> <registers...>`:

- `A5 01 01 21` frames are commands (module→main, `0A 0A` body prefix).
- `A5 01 01/00 21` frames are state reports (main→module, `0C 0C` body prefix).
- `A5 01 01/00 23` frames are short request/keep-alive/ACK (echo the sequence
  number); a long 211-byte `0x23` variant carries MCU identity
  (`ACMCU/V9-R10FT27AC-FV001.001.030`) at cold start.
- CRC-16/XMODEM over header (8 bytes) + body, excluding the two CRC bytes.

### Confirmed register map

| Register | Meaning | Values |
|----------|---------|--------|
| `0x0001` | Power | `0` off, `1` on |
| `0x0002` | Setpoint | 4-byte big-endian, hundredths of °C (e.g. `0x00000960` = 24.00 °C) |
| `0x0005` | Fan | `0` auto, `1` mute, `2` low, `3` mid-low, `4` mid, `5` mid-high, `6` high, `7` strong |
| `0x000E` | Left-right direction | `2` left, `3` middle, `4` right, `9` left-fix, `0x0A` a-bit-left, `0x0B` middle-fix, `0x0C` a-bit-right, `0x0D` left-right flow |
| `0x0011` | Vertical direction | `1` flow, `2` up, `3` down, `9` up-fix, `0x0A` above-fix, `0x0B` middle-fix, `0x0C` above-down-fix, `0x0D` down-fix |
| `0x0012` | Mode | `0` auto, `1` cool, `2` dry, `3` fan-only, `4` heat |
| `0x0013` | Eco | `0` off, `1` on (forces target to 79 °F floor) |
| `0x001E` | Light | `0` off, `1` on |
| `0x0022` | Sleep | `0` off, `1` standard, `2` aged, `3` child |
| `0x0025` | Beep | `0` off, `1` on |
| `0x0027` | Drying | `0` off, `1` on |
| `0x002D` | Generator | `1` LV1, `2` LV2, `3` LV3 |
| `0x0227` | Displayed °F | 4-byte big-endian (read-only, displayed Fahrenheit) |
| `0x00DF` | Eco mirror | mirrors `0x0013` |
| `0x0039` | Capability/list block | variable-length, seen at startup |
| `0x0003`, `0x000D`, `0x0060`, `0x0065` | observed, not yet mapped | — |

Notes:
- `auto` fan (`0x0005 = 0`) may carry a trailing `0x01` behavior flag in captures;
  the current firmware sends the bare code. Confirm before relying on auto.
- Eco is exposed as a switch; its 79 °F target clamp is **not** enforced in
  firmware (the board applies the constraint itself).

## ESPHome firmware

`esphome/rovsun-c3.yaml` wires the component to the UART and defines the
entities; `esphome/components/rovsun_a5/` contains the implementation
(`rovsun_a5.{h,cpp}` controller + `rovsun_climate.{h,cpp}` climate platform).

Exposed entities:
- **climate**: `Rovsun Mini-Split` — modes (off/auto/cool/dry/fan-only/heat),
  8 fan speeds, 8 vertical swing positions, target 16–30 °C.
- **switch**: Beep (`0x0025`), Light (`0x001E`), Drying (`0x0027`), Eco (`0x0013`).
- **select**: Sleep Mode (`0x0022`), Generator Mode (`0x002D`), Left-Right
  Direction (`0x000E`).

Component options (under `rovsun_a5:`):
- `restore_on_power_on` (default `true`): replay cached settings on power-on.
- `log_raw` (default `false`): log every RX/TX frame as hex at DEBUG level for
  later protocol analysis. Enable with a `logger` level of `DEBUG` (or lower).

### Control-flow model

1. Send a command frame.
2. The board beeps / responds immediately (evidence of receipt, not confirmed
   state).
3. A `0x21` report follows; the firmware publishes that authoritative state.
4. The board also streams periodic `0x21` reports (~every 29 s), so external
   changes (IR remote, front panel) are reconciled without polling.

### Potential features (not yet implemented)

- **Persist desired settings to flash.** Caches are currently RAM-only, so they
  are lost on an ESPHome restart. This means restore-on-power-on works while
  ESPHome stays running (breaker cycle, IR power-on), but if the ESPHome device
  also restarts during a power loss, the first-contact replay has no cached
  values to send. Saving the caches via ESPHome's `preferences` (wear-leveled
  flash) would make the desired state survive a full power+restart cycle.
- **Read-only sensors** for the unmapped registers (`0x0003`, `0x000D`,
  `0x0060`, `0x0065`, displayed °F `0x0227`) once their meaning is confirmed
  (e.g. ambient temperature, runtime).
- **ACK sequence verification**: match the echoed `0x23` sequence number before
  treating a command as delivered.
- **Auto-fan flag**: confirm whether `auto` requires the trailing `0x01` flag
  byte and send the full form if so.

## Captures & analysis tools

Raw UART captures are archived under `captures/` (one file per direction, baud
and framing in the filename). See `AGENTS.md` for capture-retention rules
(preserve originals, redact credentials/MACs/IPs, prefer Git LFS for large
files) and `README` history for the decode notes that produced this map.

- `tools/tuya-baud-detector.py` — passive host-side baud/framing detector
  (`--protocol a5`, can save raw streams).
- `tools/a5-stream-inspector.py` — offline A5 stream splitter / sequence
  inspector (validates CRC).
- `tools/rovsun-state-decoder.py` — read-only decoder for confirmed state fields.
- `tools/rovsun-command-builder.py` — offline command template builder with CRC
  recalculation (never opens a port).
- `sniff/rovsun-promicro-tx/rovsun-promicro-tx.ino` — guarded 5 V Pro Micro
  sketch that confirmed the first end-to-end command.

## Safety

- The mini-split contains mains voltage. Wire only to verified low-voltage points,
  with power disconnected while wiring.
- Do not inject serial commands while the stock module is connected (two TX
  sources cause bus contention).
- Confirm signal voltage before connecting any 3.3 V input.
- RTL8720CF is not an ESP32; the replacement strategy is to remove the module and
  speak to the main MCU UART.
