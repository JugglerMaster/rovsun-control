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
  `climate` entity (power, mode, fan, setpoint, and swing modes for air
  direction) plus switches and selects for the remaining confirmed controls.
  State is published from the board's `0x21` reports, so IR-remote changes are
  observed and reconciled.
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

> **ESPHome version:** built and verified against **ESPHome 2026.7.4**. The
> `climate` platform uses the current enum + custom-fan-mode API, so a container
> running a much older build (e.g. 2026.1.x) will fail to compile. Update your
> ESPHome (or rebuild the add-on/container) before adopting the firmware.

> **Safety: the board side is 5 V.** The XIAO's GPIOs are 3.3 V and will be
> damaged by a direct 5 V connection. The level shifter is mandatory in the path,
> and you must confirm the XIAO never sees 5 V on its pins:
> 1. Build the shifter on a breadboard **with no connection to the mini-split**.
> 2. Power the shifter's **HV side from a 5 V source** (the board rail, or a bench
>    5 V supply) and the **LV side from the XIAO's 3.3 V**.
> 3. With a multimeter / scope, verify the **LV-side** TX and RX pads sit at
>    ~3.3 V, not 5 V. If you measure 5 V on the LV side, the shifter channels are
>    crossed or wired backwards — fix before connecting the XIAO.
> 4. Only after that check, connect the LV side to the XIAO and the HV side to the
>    mini-split's JST.

### Wiring (XIAO C3)

| XIAO C3 (LV, 3.3 V) | Level shifter | Mini-split (HV, 5 V) |
|---------------------|---------------|----------------------|
| D7 GPIO20 (TX1)     | LV-TX → HV-TX | main-MCU RX (idle pin) |
| D6 GPIO21 (RX1)     | LV-RX → HV-RX | main-MCU TX (streaming pin) |
| 3V3                 | LV VCCA       | — |
| 5V (board rail)     | HV VCCB       | board 5 V |
| GND                 | GND           | board GND |

The shifter channels are **crossed**: the controller's TX drives the device's RX
(up-shift on the LV→HV direction) and the device's TX drives the controller's RX
(down-shift on HV→LV). HV must be powered by 5 V, never tied to 3.3 V.

Flash with `esphome run esphome/rovsun-c3.yaml` (USB-C). Secrets live in
`esphome/secrets.yaml`. The `external_components` block points at this GitHub
repo, so the `rovsun_a5` component is fetched automatically — you only need to
drop the YAML (and your `secrets.yaml`) into the ESPHome config directory, no
manual `components/` copy required.

### Secrets (`esphome/secrets.yaml`)

Create `esphome/secrets.yaml` next to the config. It must define every `!secret`
reference used by the YAML:

```yaml
# 32-byte base64 key for the ESPHome native API encryption.
api_key: "REPLACE_WITH_GENERATED_KEY"
wifi_ssid: "YOUR_WIFI_SSID"
wifi_password: "YOUR_WIFI_PASSWORD"
ap_password: "YOUR_FALLBACK_AP_PASSWORD"
```

Generate the `api_key` (a 32-byte base64 value) with either:

```bash
python3 -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
# or
openssl rand -base64 32
```

The `api:` component is required for two things:

- **Home Assistant API** — copy the same `api_key` into HA when adding the device
  (Settings → Devices & Services → ESPHome → enter the key).
- **Network log streaming** — `esphome logs esphome/rovsun-c3.yaml --device <ip>`
  and the dashboard "Logs" button both need the API. If you see
  *"Cannot view logs over the network: no 'api:' component is configured"*, the
  running firmware was built without `api:` (e.g. the key/secret was missing) — add
  the key above and reflash.

Keep `secrets.yaml` out of version control (it holds credentials). Do **not**
commit it.

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
- Eco (`0x0013`) is a confirmed register but is intentionally **not** exposed as
  an entity; its 79 °F target clamp is applied by the board itself.

## ESPHome firmware

`esphome/rovsun-c3.yaml` wires the component to the UART and defines the
entities; `esphome/components/rovsun_a5/` contains the implementation
(`rovsun_a5.{h,cpp}` controller + `rovsun_climate.{h,cpp}` climate platform).

Exposed entities:
- **climate**: `Rovsun Mini-Split` — modes (auto/cool/dry/fan-only/heat; power is
  a separate switch, no OFF in the mode list), 8 custom fan speeds, target
  16–30 °C, and swing modes (Off / Vertical / Horizontal / Both) for air
  direction, mapped to the AC's vertical (`0x0011`) and horizontal (`0x000E`)
  "flow" values.
- **switch**: Power (`0x0001`), Beep (`0x0025`), Light (`0x001E`), Drying (`0x0027`).
- **select**: Sleep Mode (`0x0022`), Generator Mode (`0x002D`), Left-Right
  Direction (`0x000E`), Vertical Direction (`0x0011`). These two direction
  selects give the full 8-position louver parking; the climate swing control is
  the quick on/off-per-axis alternative.

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
