# rovsun-control

Local control of a Rovsun mini-split that ships with a Realtek **RTL8720CF**
Wi-Fi module. The module talks to the main control board over a **custom `A5`
UART protocol** (not the Tuya `55 AA` MCU protocol), running at **115200 8N1**.
The stock module can be replaced by a Seeed XIAO ESP32-C6 running an ESPHome
external component (`esphome/components/rovsun_a5`) that speaks this protocol
directly, removing the cloud/app dependency.

## Status

- **Protocol decoded and confirmed** (2026-08-07): bidirectional `A5 01 01 21`
  command frames and `0x21` state reports, CRC-16/XMODEM over the header + body
  (CRC bytes excluded). Setting commands use an `0A 0A` body prefix; the board
  acknowledges with a `0x23` frame echoing the sequence number and then applies
  the change in a `0x21` report.
- **Working ESPHome firmware** (`esphome/rovsun-c3.yaml` + component): a single
  `climate` entity (power is the OFF mode; plus mode, fan, setpoint) plus
  switches and selects for the remaining confirmed controls. Air direction is
  exposed as two full-list selects (vertical + horizontal), not a swing mode.
  State is published from the board's `0x21` reports, so IR-remote changes are
  observed and reconciled.
- **Restore-on-power-on**: the controller caches every value commanded through
  ESPHome and replays them when it detects a power **off→on** transition (power
  restored, or the IR remote turning the unit on). This re-asserts HA's desired
  fan / swing / beep / light / drying / eco / sleep / generator / left-right /
  mode / setpoint, which the unit otherwise loses (it returns to factory defaults
  on power loss, and IR power-on applies the remote's stored config).

See [Protocol reference](#protocol-reference) for the full confirmed register map.

## Home Assistant dashboard

The firmware exposes the unit as separate `select` / `number` / `switch`
entities (Mode, Fan, Target Temperature, Eco, Sleep Mode, Generator Mode, the
two 8-position air-direction selects, plus power/beep/light/drying) rather than a
single `climate` entity, so a thermostat-style card does not apply. `Target
Temperature` is a `number` (whole °F, 60–90) for exact entry, and the `Temp +` /
`Temp −` buttons nudge it by ±1 °F. To show all controls in one card, group those
entities with a built-in `entities` card (no
HACS) or a `stack-in-card` + Mushroom layout. A ready-to-paste example of both
is in [`docs/ha-card-example.yaml`](docs/ha-card-example.yaml).

## Hardware

- Seeed XIAO ESP32-C6 (native USB-C, Wi-Fi, 3.3 V logic) is the preferred
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

### Wiring (XIAO C6)

| XIAO C6 (LV, 3.3 V) | Level shifter | Mini-split (HV, 5 V) |
|---------------------|---------------|----------------------|
| D7 GPIO17 (TX1)     | LV-TX → HV-TX | main-MCU RX (idle pin) |
| D6 GPIO16 (RX1)     | LV-RX → HV-RX | main-MCU TX (streaming pin) |
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

### Cold-start sequence

The repeat cold-start captures are preserved under
[`captures/cold-startup/`](captures/cold-startup/). After power restoration,
the observed order is an initial `A5 01 00 21 ... 11 11` query, full `0x21`
`0C 0C` state reports beginning about 5.2 seconds later, and a 211-byte
`A5 01 00 23` metadata frame at about 7.8 seconds. The metadata includes the
MCU identity `ACMCU/V9-R10FT27AC-FV001.001.030`. Three repeat captures are
retained with both directions and timestamp sidecars.

### Confirmed register map

| Register | Meaning | Values |
|----------|---------|--------|
| `0x0001` | Power | `0` off, `1` on |
| `0x0002` | Setpoint (target, *reported echo*) | 4-byte big-endian, hundredths of °C (e.g. `0x00000960` = 24.00 °C). Read-only from the app's perspective — writing it is a no-op. The actual setpoint *control* is `0x0227` (whole °F). |
| `0x0003` | Current / ambient temperature | 4-byte big-endian, hundredths of °C (e.g. `0x0000092C` = 23.48 °C); used by the `Current Temperature` sensor |
| `0x0005` | Fan | `0` auto, `1` mute, `2` low, `3` mid-low, `4` mid, `5` mid-high, `6` high, `7` strong |
| `0x000D` | Power / energy report | 4-byte big-endian, **best-effort / not surfaced** (observed `3592`; later seen as a stale garbage value `16780802` that never updates — not exposed as an entity) |
| `0x000E` | Left-right direction | `1` left-right flow (auto swing, **confirmed working**), `2` left flow, `3` middle flow, `4` right flow, `9` left-fix, `0x0A` a-bit-left, `0x0B` middle-fix, `0x0C` a-bit-right, `0x0D` **right-fix** (**capture-confirmed**: `0x0D` observed during a bit-right→flow louver move in `captures-air-lr-bitright-to-flow`); `8` is the rest/default position (not an app-exposed state) |
| `0x0011` | Vertical direction | `1` Up-Down Flow (auto swing), `2` Up Flow, `3` Down Flow, `9` up-fix, `0x0A` above-fix, `0x0B` middle-fix, `0x0C` above-down-fix, `0x0D` down-fix; `8` is the rest/default position (not an app-exposed state) |
| `0x0012` | Mode | `0` auto, `1` cool, `2` dry, `3` fan-only, `4` heat |
| `0x0013` | Eco | `0` off, `1` on (forces target to 79 °F floor) |
| `0x001E` | Light | `0` off, `1` on |
| `0x0022` | Sleep | `0` off, `1` standard, `2` aged, `3` child |
| `0x0025` | Beep | `0` off, `1` on |
| `0x0027` | Drying | `0` off, `1` on |
| `0x002D` | Generator | `0` off/rest, `1` LV1, `2` LV2, `3` LV3 |
| `0x0227` | Displayed °F | 4-byte big-endian (observed `79` / `74`; the value the unit shows on its panel); exposed as the `Raw 0x0227` diagnostic sensor |
| `0x00DF` | Eco mirror | mirrors `0x0013` |
| `0x0008` | Capability / list block | variable-length array (**not** a register/value pair); the firmware resyncs past it in the `0x21` secondary report |

**Still-unmapped but observed** (under study): `0x000C`, `0x0015`, `0x0017`,
`0x0035`, `0x0038`, `0x0055`, `0x005C`, `0x005E`, `0x0072`–`0x0074`, `0x0095`,
`0x00C9`, `0x0148`. All are exposed as **disabled-by-default diagnostic sensors**
via the `raw_registers` watcher (see below) so their behaviour can be correlated
with unit actions. (`0x0060` / `0x0065` were noted earlier but have **not**
appeared in the current captures.)

Notes:
- Recovered baseline/startup reports contain `0x000E = 0x08` and
  `0x0011 = 0x08`; these are observed rest/default values, but their UI names
  are not yet confirmed. The controlled horizontal transitions confirm the
  selectable values `0x02` through `0x0D` listed above.
- A later Pro Micro/Tuya capture recorded an additional horizontal command
  `0A 0A 00 0E 01`. This is the inferred ninth raw horizontal state; its UI
  name is not confirmed, so it remains available through the temporary raw
  code control rather than the named select. `0x0E` itself has not appeared.
- Generator captures show `0x002D = 0x00` in the off/rest state and
  `0x002D = 0x01` for LV1. The ESPHome mapping therefore treats zero as a real
  `off` option and sends it when selected.
- `auto` fan (`0x0005 = 0`) may carry a trailing `0x01` behavior flag in captures;
  the current firmware sends the bare code. Confirm before relying on auto.
- Eco (`0x0013`) is exposed as an `off`/`on` select; its 79 °F target clamp is
  applied by the board itself, not in firmware.
- The `0x21` secondary report embeds the `0x0008` capability blob. Because it is
  variable-length and not register/value pairs, a naive parser desyncs after it
  (emitting spurious registers such as a bogus `0x0005 = 0`). `parse_frame_()`
  detects `0x0008` and resyncs to the next known register before continuing.
 - The 4-byte registers are `0x0002`, `0x0003`, `0x000D`, `0x0227`; every other
   observed register is a single byte.

### Remote button → register cross-reference

Derived from `Manuals/Mini-split-remote.md`. **Confirmed** rows are wired in the
firmware / observed in captures; **Hypothesized** rows are inferred from the
manual's feature descriptions and still need a button-press capture to confirm
(see [Captures & analysis tools](#captures--analysis-tools)).

| Remote button / feature | Register | Status | Notes |
|-------------------------|----------|--------|-------|
| Power | `0x0001` | Confirmed | `0` off, `1` on |
| MODE (AUTO/COOL/DRY/FAN/HEAT) | `0x0012` | Confirmed | values `0`–`4` |
| TEMP ▲ / ▼ (setpoint) | `0x0227` | Confirmed | Whole degrees **°F** (e.g. `75` = 75 °F). The OEM app writes only `0x0227` to change the target; `0x0002` is the resulting °C echo. |
| FAN (auto/mute/low/…/high/**turbo**) | `0x0005` | Confirmed | `0` auto, `1` mute, `2` low, `3` mid-low, `4` mid, `5` mid-high, `6` high, **`7` = TURBO** (firmware labels `7` "strong" — should be "turbo") |
| SWING ▲▼ (vertical louver) | `0x0011` | Confirmed | |
| SWING ◀▶ (horizontal louver) | `0x000E` | Confirmed | |
| MUTE (quiet fan) | `0x0005` = `1` | Confirmed | MUTE is a fan speed, not a separate register |
| ECO | `0x0013` | Confirmed | long-press ECO = 8 °C heating (separate function — see below) |
| SLEEP | `0x0022` | Confirmed | `0` off, `1` standard, `2` aged, `3` child |
| BUZZER | `0x0025` | Confirmed | firmware "Beep" |
| DISPLAY (LED panel on/off) | `0x001E` | Hypothesized | firmware labels it "light"; likely the panel LED, not room lighting |
| GEN / GENERATOR (long-press MUTE 3 s) | `0x002D` | Confirmed | `0` off, `1` LV1, `2` LV2, `3` LV3; default is off |
| °C/°F display switch (long-press TURBO/FAN) | `0x0227` | Confirmed (reuse) | `0x0227` is the target-temperature register; the OEM app writes it as whole °F to set the setpoint (observed `74`/`75` for a 74→75 °F change). The AC also reports it back alongside the `0x0002` °C echo. |
| 8 °C heating (long-press ECO) | — | Unknown | not yet seen in captures; likely a distinct register/flag |
| I FEEL (remote temp sensing) | — | Unknown | candidate: one of `0x000C` / `0x0072`–`0x0074` / `0x0095` |
| HEALTH (ionizer) | — | Unknown | |
| GENTLE WIND (FAN+MUTE long-press) | — | Unknown | |
| SELF-CLEAN (SWING combo) | — | Unknown | |
| CHILD LOCK (MODE+TIMER) | — | Unknown | |
| ANTI-MILDEW | — | Unknown | appears on remote LCD icon list; may be a state flag |
| AUTO GEN / VOICE / BLUETOOTH / RESET Wi-Fi | — | Unknown | model-dependent; not yet observed |

The "Unknown" rows are the best candidates for the still-unmapped registers
(`0x000C`, `0x0015`, `0x0017`, `0x0035`, `0x0038`, `0x0055`, `0x005C`, `0x005E`,
`0x0072`–`0x0074`, `0x0095`, `0x00C9`, `0x00DF`, `0x0148`). Capturing each
button press individually and diffing the `0x21` frames will map them.

## ESPHome firmware

`esphome/rovsun-c3.yaml` wires the component to the UART and defines the
entities; `esphome/components/rovsun_a5/` contains the implementation
(`rovsun_a5.{h,cpp}` controller + `rovsun_climate.{h,cpp}` climate platform).

Exposed entities:
- **climate**: `Rovsun Mini-Split` — the OFF mode is the power button; other
  modes are auto/cool/dry/fan-only/heat. 8 custom fan speeds, target 16–30 °C.
- **switch**: Beep (`0x0025`), Light (`0x001E`), Drying (`0x0027`).
- **select**: Sleep Mode (`0x0022`), Eco (`0x0013`, off/on), Generator Mode
  (`0x002D`), Left-Right Direction (`0x000E`), Vertical Direction (`0x0011`).
  These two direction selects expose the full louver list for each axis —
  every fixed position **plus** the "flow" (swing) value — so you get a long
   option list per direction instead of a simplified swing control.

### Deployment

The firmware is deployed to the units with **ESPHome** — there is no separate
build step or flash tool; the `esphome` CLI compiles and uploads the config
directly to each device over USB/serial. This repo's `esphome/` configs are
the source of truth; running the ESPHome script against a config *is* the
deploy.

Prerequisites:
- `esphome/secrets.yaml` must exist (WiFi `ssid`/`password`, per-unit
  `api_key`/`ap_key` — see [Secrets](#secrets-esphomesecretsyaml)).
- The target board is `seeed_xiao_esp32c6`; connect it over USB.

On the Windows host (per `AGENTS.md`, using the bundled Python):

```powershell
& "C:\Users\chris\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m esphome run esphome\rovsun-upstairs.yaml
& "C:\Users\chris\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m esphome run esphome\rovsun-c3.yaml
```

`run` compiles and uploads in one step. Use `compile` first if you only want
to validate the YAML before flashing. After a successful deploy, the device
rejoins WiFi and the entities appear (or update) in Home Assistant.

> **Note:** `Left-Right Direction` → `left_right_flow` currently sends a
> placeholder value (`0x01`) until its real register code is captured; all
> other direction options already send their confirmed codes.

Component options (under `rovsun_a5:`):
- `restore_on_power_on` (default `true`): replay cached settings on power-on.
- `log_raw` (default `false`): log every RX/TX frame as hex at DEBUG level for
  later protocol analysis. Enable with a `logger` level of `DEBUG` (or lower).
- `raw_registers` (optional): reverse-engineering watcher. A list of
  `{ register: <hex>, id: <sensor_id> }` entries that route **any** AC-reported
  register to a `sensor` entity, so undocumented bytes can be observed live. The
  parser treats these registers as known (never desyncs on them), and the value
  is published on change. Example:

  ```yaml
  sensor:
    - platform: template
      name: "Raw 0x0095"
      id: raw_0x0095
      entity_category: diagnostic
      disabled_by_default: true
  rovsun_a5:
    # ...
    raw_registers:
      - register: 0x0095
        id: raw_0x0095
  ```

  `esphome/rovsun-c3.yaml` already wires all currently-observed-but-unmapped
  registers this way (disabled by default); enable any of them in HA to start
  logging its history and correlate it with unit actions.

### Control-flow model

1. Send a command frame.
2. The board beeps / responds immediately (evidence of receipt, not confirmed
   state).
3. A `0x21` report follows; the firmware publishes that authoritative state.
4. The board also streams periodic `0x21` reports (~every 29 s), so external
   changes (IR remote, front panel) are reconciled without polling.

### Potential features (not yet implemented)

- **Persist desired settings to flash** — **done.** The last commanded settings
  (fan, vdir, mode, setpoint, beep, light, drying, sleep, eco, lrdir) are saved
  to ESPHome's wear-leveled `preferences` flash on every power **off** transition
  and reloaded in `setup()`. This means restore-on-power-on now also survives an
  ESPHome restart, so a breaker cycle that restarts both the unit and the
  controller still replays HA's desired state. (Generator is intentionally
  excluded, as before.) Note: an *abrupt* power loss with no graceful off report
  still keeps the previous snapshot — to also cover that, persist on each
  command instead of only on power-off.
- **Read-only sensors** — mostly done. `0x0003` (ambient temp) drives the
  `Current Temperature` sensor, and `0x0227` plus all other observed registers are
  available through the `raw_registers` watcher below. The `0x000D` power/energy
  report is **not** exposed (it never updates and has been observed as a stale
  garbage value), so there is no `Power` sensor. The only remaining gap is
  *confirming the meaning/unit* of the still-unmapped registers (esp. the
  `0x0072`–`0x0074` / `0x0227` family), which needs action-correlated captures.
- **ACK sequence verification**: match the echoed `0x23` sequence number before
  treating a command as delivered.
- **Auto-fan flag**: confirm whether `auto` requires the trailing `0x01` flag
  byte and send the full form if so.

## Captures & analysis tools

Raw UART captures are archived under `captures/` (one file per direction, baud
and framing in the filename). See `AGENTS.md` for capture-retention rules
(preserve originals, redact credentials/MACs/IPs, prefer Git LFS for large
files) and `README` history for the decode notes that produced this map.

Additional paired transition captures recovered from local OpenCode history are
under [`captures/recovered-opencode/`](captures/recovered-opencode/), with a
manifest describing the covered airflow and control transitions.

- `tools/tuya-baud-detector.py` — passive host-side baud/framing detector
  (`--protocol a5`, can save raw streams).
- `tools/a5-stream-inspector.py` — offline A5 stream splitter / sequence
  inspector (validates CRC).
- `tools/rovsun-state-decoder.py` — read-only decoder for confirmed state fields.
- `tools/rovsun-command-builder.py` — offline command template builder with CRC
  recalculation (never opens a port).
- `sniff/rovsun-promicro-tx/rovsun-promicro-tx.ino` — guarded 5 V Pro Micro
  sketch. It monitors the bus by default (frames + CRC-checked A5 decode to USB
  so you can watch the XIAO C6's commands in response to Home Assistant) and can
  still transmit for bench tests. To watch the live ESP32, tap its **D7 (GPIO17,
  TX)** into the Pro Micro **RX1/D0** with common GND and leave the Pro Micro TX
  disconnected (two TX sources on the bus cause contention).

## Safety

- The mini-split contains mains voltage. Wire only to verified low-voltage points,
  with power disconnected while wiring.
- Do not inject serial commands while the stock module is connected (two TX
  sources cause bus contention).
- Confirm signal voltage before connecting any 3.3 V input.
- RTL8720CF is not an ESP32; the replacement strategy is to remove the module and
  speak to the main MCU UART.
