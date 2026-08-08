# rovsun-control

Reverse-engineering and local control of a Rovsun mini-split that uses a
Realtek **RTL8720CF** Wi-Fi module. The app is not necessarily the Tuya app;
the device metadata mentions air-conditioning, voice control, and TCL Home BT
EZ. Those branding details do not determine the UART protocol. The working
hypothesis is that the Wi-Fi module talks to the main control board using the
Tuya MCU serial protocol, but this must be confirmed before modifying hardware.

The mini-split also has an IR remote. IR control is not integrated cleanly with
the app: commands from the app and remote can override one another, and their
state may not stay synchronized.

The exposed module header is labeled `5V TX RX GND`. With the unit powered,
both `TX` and `RX` measured approximately 5 V at idle. Treat these as 5 V TTL
signals until proven otherwise; do not connect them directly to XIAO GPIOs.

## Status

Bidirectional control over the 5 V UART is confirmed (2026-08-07). A guarded
5 V Pro Micro (ATmega32U4) sketch transmits `A5 01 01 21` command frames and
the main board acknowledges with a `0x23` frame echoing the transmitted
sequence number, then applies the setting in its `0x21` state report. The beep
register (`0x0025`) was toggled both on and off successfully, and fan speed
was set via register `0x0005`. The protocol is therefore a working local
control path that can replace the stock Wi-Fi module. See the live command test
below for the wiring and frame structure.

## Hardware you have

- Several Seeed XIAO ESP32-C3 (native USB-C, Wi-Fi, 3.3 V logic)
- USB-to-TTL serial adapter for passive UART capture
- 3.3 V/5 V UART level shifter with divided 5 V RX and transistor TX conversion
- Arduino boards are available, but the XIAO is the preferred replacement
- Two mini-splits (experiment on one, keep the other stock)

## Current network findings

The app-provided MAC address `20:f1:b2:5c:1b:3e` maps to
`192.168.1.130` on the LAN. Its `20:f1:b2` OUI is registered to Tuya Smart,
which confirms that this is a Tuya-family device. It is reachable, but it did
not respond on the usual Tuya local ports `6666`, `6667`, or `6668`, and no
Tuya discovery broadcast was observed during passive listening. This does not
rule out Tuya hardware; local control may be disabled, use a newer protocol,
or require the branded app/cloud path.

There is also a separate Midea Ubit on the network:

- `192.168.1.45`, hostname `net_ac_3A18`
- MAC prefix `24:59:e5`, registered to GD Midea Air-Conditioning Equipment
- TCP port `6444` open, consistent with Midea local control

Do not use the Midea Ubit as evidence about the Rovsun unit. They are separate
hardware and protocol families.

## Phase 1 — optional network investigation

If the branded app can provide a Tuya local key, test the LAN path without
modifying the mini-split:

```bash
pip install tinytuya
tuya wizard        # only works if the device is accessible through Tuya
# dump live datapoints to learn the DP mapping:
python3 -c "import tinytuya; d=tinytuya.Device('DEVICE_ID','192.168.1.130','LOCAL_KEY'); print(d.status())"
```

If this fails, do not brute-force commands or inject traffic into the device.
Proceed to passive UART capture instead. The local key is not required for the
hardware replacement path.

## Phase 2 — prove the UART protocol

This is the primary validation step. Keep the stock module installed and the
mini-split unmodified. The RTL8720CF has two UART directions:

- Module TX -> main-board RX
- Main-board TX -> module RX

The USB-to-TTL adapter can capture one direction at a time:

| USB-to-TTL adapter | Connection |
|--------------------|------------|
| RX                 | module TX  |
| GND                | verified board signal GND |
| TX                 | leave disconnected |
| VCC                | leave disconnected |

Current capture wiring note: on the mini-split side, blue is connected to board
signal GND and yellow is connected to the module TX signal. Connect blue to the
adapter GND and yellow to the adapter RX. Do not connect the adapter TX or VCC.

First capture the module TX line, then move the adapter RX lead to the module
RX line and repeat after a power cycle. With two adapters, connect one adapter
RX to each direction and leave both adapter TX pins and VCC disconnected. Try
`9600`, `19200`, and `115200` baud, using `8N1`. Clean frames beginning with
`55 AA` confirm the Tuya MCU protocol. Save raw captures or decoded bytes so
the baud rate, commands, checksums, and datapoints can be reviewed before any
replacement is attempted.

The passive host-side detector can capture both directions at once. Install
`pyserial`, then run it with the two raw receive ports:

```bash
python3 -m pip install pyserial
python3 tools/tuya-baud-detector.py /dev/ttyUSB0 /dev/ttyUSB1 --duration 10 --verbose
```

It only reads; unlike generic baud detectors it never sends `AT` or any other
probe. By default it reports only checksum-valid Tuya `55 AA` frames. For the
observed Rovsun protocol, use raw mode or the lightweight `A5` marker mode and
save each stream for later decoding:

```bash
python3 tools/tuya-baud-detector.py COM6 COM8 --protocol a5 \
  --baudrates 115200 --duration 30 --verbose --raw-dir captures
```

The Arduino Micro/Leonardo logger on `COM8` emits captured UART bytes unchanged;
the CP2102 on `COM6` should be connected to the other direction. Use `--all`
for unusual rates or `--baudrates 9600,19200,115200` to specify an exact list.
A quiet bus can produce no result, so repeat the scan across a power cycle or
increase `--duration`.

Native-USB Micro/Leonardo boards require DTR for their USB CDC data endpoint.
Include the logger port with `--dtr-ports`; this resets it and waits six seconds
for the logger to start:

```bash
python3 tools/tuya-baud-detector.py COM6 COM10 --protocol a5 \
  --dtr-ports COM10 --baudrates 115200 --duration 30 --raw-dir captures \
  --timestamp-dir captures
```

The detector keeps DTR/RTS deasserted on ordinary USB-TTL adapters. The native
USB board can briefly unregister or receive a new COM number during reset, so
use its currently enumerated port.

`--timestamp-dir` writes one TSV row per received chunk with elapsed seconds
and hex bytes. It is useful for measuring idle heartbeat intervals; timestamps
are chunk-level because USB serial drivers may deliver several UART bytes at
once.

Inspect saved raw streams without touching the hardware:

```bash
python3 tools/a5-stream-inspector.py captures-fan-change/COM6_115200_8N1.bin \
  captures-fan-change/COM10_115200_8N1.bin
```

The inspector uses the declared total frame length at byte 7, reports command
and normalized sequence fields, and preserves candidate bytes for later
checksum analysis. It falls back to the next `A5` marker for incomplete or
invalid candidates. It does not open ports or transmit anything.

The current captures establish that bytes 8-9 are a big-endian CRC-16/XMODEM
calculated over the frame with those two CRC bytes removed. The inspector marks
frames with `crc=ok` or `crc=BAD`.

Decode the confirmed state fields from a saved capture with:

```bash
python3 tools/rovsun-state-decoder.py captures-temp-74-to-75/COM6_115200_8N1.bin
```

The decoder is read-only and reports only fields confirmed or provisionally
mapped from captures; it does not open serial ports or send commands.
On a cold-start capture it also reports the MCU identity from the long startup
metadata frame while intentionally omitting the adjacent configuration strings.

Build an offline candidate command from a captured module-to-main template:

```bash
python3 tools/rovsun-command-builder.py captures-temp-74-to-75/COM10_115200_8N1.bin \
  --replace 0x0227=0000004B --sequence 0xAA
```

The builder only prints or writes bytes and never opens a serial port. Do not
connect its output to the mini-split until command arbitration and stock-module
isolation have been independently verified.

CRC validation currently passes on 63 complete frames with zero failures. The
short `0x23` frames are 12 bytes long and carry nearly fixed data (`80 0A`,
`80 0C`, or `80 0D`) after the CRC; their changing two-byte fields are therefore
not temperature or fan values. State changes appear in the variable-length
`0x21` reports, which contain recurring register/list blocks that still need to
be mapped.

Normal `0x21` report bodies begin with `0C 0C` and commonly contain 6-byte
register/value blocks, including recurring registers `0x0002`, `0x0003`,
`0x0005`, `0x000D`, `0x0011`, `0x0060`, and `0x0065`. Larger reports also carry
a variable-length capability/list block beginning at register `0x0039`. These
are provisional structural observations; register meanings require controlled
state captures.

A saved `74 F -> 75 F` capture isolated two likely target-temperature fields in
the `0x21` report: register `0x0002` contained `00 00 09 60` (2400, plausibly
24.0 C in hundredths) and register `0x0227` contained `00 00 00 4B` (75 decimal,
likely the displayed Fahrenheit value). Confirm this mapping with the reverse
temperature transition before using it for control. The reverse `75 F -> 74 F`
capture produced `0x0002 = 00 00 09 2E` (2350, plausibly 23.5 C) and
`0x0227 = 00 00 00 4A` (74), confirming both fields.

Operating-mode comparison identified register `0x0012`: cooling is `0x01`, dry
is `0x02`, and the earlier fan-only capture carried `0x03`. The changed
`0x000D` bytes seen in earlier mode captures track other airflow/state values
and are not the operating-mode field.

The app's operating-mode list is `auto`, `cool`, `dry`, `fan`, and `heat`.
The cool to auto capture produced `00 12 00`, identifying auto as `0x00`, and
the auto to heat capture produced `00 12 04`, identifying heat as `0x04`. The
complete observed mode table is auto `0x00`, cool `0x01`, dry `0x02`, fan
`0x03`, and heat `0x04`. The heat capture also included a separate 79 F to 78 F
temperature change; that did not affect the mode field. Auto may already engage
heating or cooling based on demand, so its physical behavior is not equivalent
to explicit heat mode.

The final power transition identified register `0x0001`: the on report starts
with `00 01 01`, while the off report is `00 01 00 00 38 00`. The first value
byte therefore maps power on to `0x01` and off to `0x00`.

Direction analysis separates commands from reports. Setting commands appear on
the module-to-main stream as `A5 ... 21` frames with an `0A 0A` body prefix;
the main-board-to-module stream returns `A5 ... 21` state reports with the
usual `0C 0C` prefix. The short `0x23` frames are request/metadata activity,
not the setting command itself. Do not connect a TX path until this command
direction and the complete frame response behavior are validated.

Fan captures provisionally identify register `0x0005` as a fan-control field.
The mute to low-wind capture produced `00 05 02 00 73 00`, while the reverse
low-wind to mute capture produced `00 05 01 00 73 00`. This confirms distinct
codes `0x01` (mute candidate) and `0x02` (low wind). An earlier `0x07` sample
was misattributed to low wind and remains unidentified. Do not collapse the
app's labels into generic low/medium/high values. The low-wind to `auto`
capture produced `00 05 00 00 73 01`; in this device, `auto` means a fixed fan
speed with compressor control responding to cooling demand, not automatic fan
speed selection. Treat the trailing `0x01` as an auto-behavior flag candidate.
The auto to mid-wind capture produced `00 05 04 00 73 00`, identifying `0x04`
as the mid-wind speed code and confirming the auto flag clears for a normal
speed selection. The mid-wind to mid-low-wind capture produced
`00 05 03 00 73 00`, identifying `0x03` as the mid-low-wind code.
The mid-low-wind to mid-high-wind capture produced `00 05 05 00 73 00`,
identifying `0x05` as the mid-high-wind code.
The mid-high-wind to high-wind capture produced `00 05 06 00 73 00`,
identifying `0x06` as the high-wind code.
The high-wind to strong-wind capture produced `00 05 07 00 73 00`,
identifying `0x07` as the strong-wind code. The observed fan table is now:
`0x01` mute, `0x02` low wind, `0x03` mid-low wind, `0x04` mid wind, `0x05`
mid-high wind, `0x06` high wind, and `0x07` strong wind. Auto uses `0x00` with
the separate behavior flag `0x01`.

The app exposes additional controls that should be mapped independently:
sleep, eco, timer, fan mute, airflow direction, beep, light, generator mode,
drying, and electricity monitoring, with potentially more device-specific
options. Sleep has three app modes: `standard`, `aged`, and `child`. Its fan
selector has eight distinct labels: `strong wind`, `high wind`,
`mid high wind`, `mid wind`, `mid low wind`, `low wind`, `mute`, and `auto`.
Both the app and IR remote can set sweep, but only the app provides independent
airflow direction control. Keep these distinctions in the capture notes;
app-only features may have UART datapoints that cannot be reproduced through the
remote.

The app has separate eight-option airflow axes. Up-down options are `up-down
flow`, `up flow`, `down flow`, `up fix`, `above fix`, `middle fix`, `above down
fix`, and `down fix`. Left-right options are `left-right flow`, `left flow`,
`middle flow`, `right flow`, `left fix`, `a bit left fix`, `middle fix`, and `a
bit right fix`.

The timer is an app-level schedule that combines power on/off, airflow settings,
fan speed, temperature, repeat days, and time. Treat it as a collection of
scheduled commands rather than a single UART setting.

The first sleep capture used `standard` and showed a new `00 22 01` field.
That makes `0x01` the standard-mode candidate, not a generic boolean. Map
`aged` and `child` before assigning the remaining values. The standard to aged
capture changed the field to `00 22 02`, identifying `0x02` as the aged-mode
candidate. The aged to child capture produced `00 22 03`, identifying `0x03`
as the child-mode candidate. Returning child sleep to off produced `00 22 00`,
confirming the complete mapping: off `0x00`, standard `0x01`, aged `0x02`, and
child `0x03`.

Eco captures showed matching state flags at `0x0013` and `0x00DF`: both were
`0x01` with Eco enabled and `0x00` with Eco disabled. Enabling Eco also moves
the target to `79 F` and prevents setting it below `79 F`; this is a behavior
constraint in addition to the flag.

The beep off to on capture showed `00 25 01`, making register `0x0025` the beep
setting candidate with `0x01` enabled. The reverse capture showed `00 25 00`,
confirming `0x00` disabled.

The light off to on capture showed `00 1E 01`, making register `0x001E` the
light setting candidate with `0x01` on. The reverse capture showed `00 1E 00`,
confirming `0x00` off.

The first up-down airflow transition (`up-down flow` to `up flow`) produced
`00 11 02`, making register `0x0011` the up-down direction candidate with
`0x02` likely representing up flow. The remaining up-down values still need
controlled captures. The up-flow to down-flow transition produced `00 11 03`,
identifying `0x03` as the down-flow candidate. A clean repeat confirmed that
value, and the down-flow to up-fix capture produced `00 11 09`, identifying
`0x09` as the up-fix candidate. The up-fix to above-fix capture produced
`00 11 0A`, identifying `0x0A` as the above-fix candidate. The above-fix to
middle-fix capture produced `00 11 0B`, identifying `0x0B` as the middle-fix
candidate. The middle-fix to above-down-fix capture produced `00 11 0C`,
identifying `0x0C` as the above-down-fix candidate.
The above-down-fix to down-fix capture produced `00 11 0D`, identifying
`0x0D` as the down-fix candidate. Confirm the default up-down-flow value before
committing the full axis table. The down-fix to up-down-flow capture produced
`00 11 01`, completing the observed table: flow `0x01`, up `0x02`, down `0x03`,
up fix `0x09`, above fix `0x0A`, middle fix `0x0B`, above-down fix `0x0C`, and
down fix `0x0D`.

The first left-right airflow transition (`left-right flow` to `left flow`)
produced `00 0E 02`, making register `0x000E` the left-right direction
candidate with `0x02` likely representing left flow. The remaining left-right
values still need controlled captures. The left-flow to middle-flow transition
produced `00 0E 03`, identifying `0x03` as the middle-flow candidate.
The middle-flow to right-flow transition produced `00 0E 04`, identifying
`0x04` as the right-flow candidate. The right-flow to left-fix transition
produced `00 0E 09`, identifying `0x09` as the left-fix candidate on the
left-right register.
The left-fix to a-bit-left-fix transition produced `00 0E 0A`, identifying
`0x0A` as the a-bit-left-fix candidate on the left-right register.
The a-bit-left-fix to middle-fix transition produced `00 0E 0B`, identifying
`0x0B` as the middle-fix candidate on the left-right register.
The middle-fix to a-bit-right-fix transition produced `00 0E 0C`, identifying
`0x0C` as the a-bit-right-fix candidate on the left-right register.
The a-bit-right-fix to left-right-flow transition produced `00 0E 0D`,
completing the observed left-right table: left flow `0x02`, middle flow `0x03`,
right flow `0x04`, left fix `0x09`, a bit left fix `0x0A`, middle fix `0x0B`,
a bit right fix `0x0C`, and left-right flow `0x0D`.

The cold-start capture showed startup traffic distinct from normal operation:
an initial `A5 01 00 21` frame, full `0x21` state reports beginning about 5.2
seconds after power restoration, and a 211-byte `A5 01 00 23` metadata frame.
The metadata includes MCU identity `ACMCU/V9-R10FT27AC-FV001.001.030` and
appears to contain module configuration strings. Thus `0x23` is usually a
12-byte request/keep-alive, but startup also uses a long metadata variant that
must be preserved by the decoder.

A second cold-start capture reproduced the same handshake order, full-report
sequence, and MCU identity. Absolute timestamps shifted by about one second
with the power-restore timing, but the startup structure was otherwise stable.
A third cold-start capture reproduced the same sequence again, including the
same long metadata frame and MCU identity. Startup behavior is now sufficiently
repeatable for initialization logic design.

Generator mode is a three-level setting rather than a boolean. The initial
capture identified register `0x002D` with LV1 as `0x01`; the LV1 to LV2 capture
produced `00 2D 02`, and the LV2 to LV3 capture produced `00 2D 03`. The
complete generator mapping is LV1 `0x01`, LV2 `0x02`, and LV3 `0x03`.

The drying off to on capture showed `00 27 01`, making register `0x0027` the
drying setting with `0x01` enabled. The reverse capture showed `00 27 00`,
confirming `0x00` disabled.

An idle dual capture showed matching `A5 01 01 21` and `A5 01 01 23` traffic at
approximately 9.8 and 38.7 seconds, about 28.9 seconds apart, on the two
directions. Separate `A5 01 00 21`/`A5 01 00 23` frames appeared around 46.7
seconds. This is consistent with periodic status/keep-alive traffic, but more
idle captures are needed before treating 29 seconds as a fixed interval.

### Control-flow reference from GREE research

The [GREE HVAC protocol research](https://github.com/bekmansurov/gree-hvac-protocol)
documents a useful control-flow model, even though it describes different
hardware and protocol framing. The GREE module sends commands or status
requests, the indoor unit applies the request and returns a status response,
and the module periodically polls so changes made by the IR remote, front-panel
buttons, or another controller are eventually observed.

Use the same behavior as the working Rovsun controller model:

1. Send a control request.
2. Treat the immediate beep or physical response as evidence that the unit
   received the request, not as confirmed application state.
3. Wait for the subsequent `A5` state report before updating the published
   state.
4. Continue periodic status or keep-alive handling so external changes are
   reconciled.

This matches the current timing observation: the Rovsun beeps nearly
immediately, begins applying the setting, and the app updates its displayed
state approximately one second later. The GREE baud rate, `7E 7E` framing,
packet fields, timing intervals, and checksum must not be reused for Rovsun;
only the separation between command delivery, confirmed state, and polling is
being used as a design reference.

### Startup behavior to capture

The [GREE wired-protocol startup discussion](https://github.com/maxim-smirnov/gree-wired-proto/issues/1)
is a reminder to capture startup separately from normal operation. That issue
does not provide usable startup logs, but the same investigation is needed for
Rovsun. Begin recording both UART directions before powering the unit, then
look for:

- boot or handshake frames before normal state traffic;
- the first complete state report after power-on;
- whether `A5 01 01 21` and `A5 01 01 23` begin immediately or only after a request;
- which direction initiates the exchange and which direction reports state;
- whether the approximately 29-second traffic is a heartbeat, status poll, or both;
- whether commands work before the periodic exchange is established.

Save the startup capture with timestamps and do not inject traffic during this
investigation. These observations will define the replacement controller's
initialization and polling sequence.

Treat each breaker cycle as a fresh baseline during testing. The mini-split is
expected to return to factory-default settings after power is removed, and the
Rovsun UART module may also restart from its defaults. Capture startup traffic
before sending commands, verify the reported initial state, and do not reuse
sequence or state assumptions from an earlier power cycle.

Test IR-originated changes separately. Change power, mode, temperature, fan,
and airflow with the IR remote while capturing both UART directions, then
verify whether the main board reports those changes to the replacement
controller. If it does, ESPHome can update its state from the UART report. If
it does not, the main board may allow IR commands to override the UART-facing
state without notification. Replacing or modifying the IR receiver is a
possible later hardware solution, but it is not part of the initial controller
design. The remote appears to retain a complete configuration: pressing its
power button can apply the remote's stored mode, temperature, fan, and other
settings rather than changing power alone. Record the remote's display before
each test and treat a power-button capture as a full-state replay, not an
isolated power datapoint. If the UART reports the replayed state, Home
Assistant could restore the preferred values with an automation, but that may
introduce a visible delay or command race. A hardware solution that intercepts
or gates the IR receiver could prevent the override more deterministically,
though it may sacrifice the original remote unless a controllable bypass is
added. Choose between these only after measuring the actual IR-to-UART timing
and reporting behavior.

The expected Tuya setting is `8N1`, which is the default. If the wiring is
correct but no valid frames are found, test framing variants explicitly:

```bash
python3 tools/tuya-baud-detector.py /dev/ttyUSB0 /dev/ttyUSB1 \
  --baudrates 9600,19200,115200 --framings 8N1,8N2,8E1,8O1 --duration 10
```

`--all-framings` also tests 7/8 data bits, none/odd/even parity, and one/two
stop bits. A valid checksum is required, so random readable bytes do not count
as a match. Stop-bit variants can be indistinguishable on a receive-only UART;
this option is a diagnostic fallback, not a reason to assume the protocol is
not `8N1`.

Initial passive capture on the module TX line produced sustained, structured
traffic at `115200 8N1`, including repeated `A5 01 01 ...` sequences (270 bytes
during an on/off test). Captures at `9600` and `19200` appeared to be random
bytes. This is active UART traffic, but it does not match the expected Tuya
`55 AA` framing; preserve captures and identify this protocol before injecting
anything.

Changing the target temperature while monitoring at `115200` produced 318
bytes and changing `A5 01 01 23 ...` packets, including successive values
`23 00 12`, `23 00 13`, and `23 00 14`. This confirms that app state changes are
visible on the captured line; the packet fields still need to be decoded.

A controlled `74 -> 75 -> 74 -> 75` sequence produced six `A5 01 01 23`
packets with counters `0x1E` through `0x23`, each followed by an `A5 01 01 21`
packet. The `0x23` packets had changing two-byte values followed by constant
`80 0A`; the `0x21` packets showed corresponding alternating status bytes.
The `0x23` and `0x21` roles are provisional until the opposite UART direction
is captured.

The opposite signal pin also carried the same `A5` protocol at `115200 8N1`
(120 bytes in a 20-second capture), but with different contents, including
`... 80 0C` where the first capture used `... 80 0A`. This confirms that both
UART directions are active and distinct; the direction roles remain provisional
until verified against the module pin labels.

Use a USB-TTL adapter whose RX input is rated for 5 V, or add a resistor divider
before its RX input. If the UART is confirmed to be 5 V, level-shift the main
board TX down to the XIAO RX, and preferably shift the XIAO TX up to 5 V before
the main-board RX. A 5 V rail on the header must never be connected to the
XIAO `3V3` pin.

With the available UART level shifter, connect the XIAO to the `LV`/3.3 V side
and the module header to the `HV`/5 V side. For the receive direction, module
`TX` -> shifter 5 V-side RX -> shifter 3.3 V-side output -> XIAO RX. For the
transmit direction, XIAO TX -> shifter 3.3 V-side input -> shifter 5 V-side TX
-> module `RX`. Follow the actual labels and direction markings on the shifter;
do not rely on the physical placement of its pins.

The XIAO can also be used as a passive serial receiver, but the USB-to-TTL
adapter is simpler for one direction and does not require flashing a sniffer.
Two receivers are needed for simultaneous two-way capture.

### JST pin map and signal directions

See `docs/wifi-module-hw-analysis.md`. The stock module is a 3.3 V Tuya TCLWBR;
the breakout up-shifts its TX (transistor pull-down, idle 5 V) and down-shifts
its RX (resistor divider). Therefore the 4-pin JST toward the main board carries
**5 V** UART on both signal pins, which is why the CP2102 (3.3 V) could not
drive it and the 5 V Pro Micro is the correct tool for live TX.

The header is labeled `5V TX RX GND`. By the Tuya pinout (module pin3 = TX,
pin4 = RX), the header `TX` pin is the module's TX output = the **main-board
RX** (the line a replacement transmits on), and the header `RX` pin is the
module's RX input = the **main-board TX** (the line a replacement receives on).
This matches the Phase 3 table (XIAO TX1 -> main-MCU RX, XIAO RX1 ->
main-MCU TX).

The stock WiFi breakout internally crosses TX/RX so the 3.3 V module sees the
correct orientation against the main board. To the replacement controller the
connection is therefore straight through relative to the main board: controller
**RX** connects to the main-board **TX** pin (the line that continuously
streams `A5 01 01 21` frames), and controller **TX** connects to the
main-board **RX** pin (idle until a command is sent). The streaming pin is the
receive side; the idle pin is the transmit side.

Definitive direction test with the stock module removed:

- One signal pin continuously streams `A5 01 01 21` / `0x23` frames
  (main-board TX). Connect the receiver (Pro Micro `RX1/D0`, CP2102 `RX`, or
  XIAO `RX1`) here.
- The other signal pin is idle/silent until a command is sent (main-board RX).
  Connect the transmitter (Pro Micro `TX1/D1` or XIAO `TX1`) here.
- Never connect the 5 V pin to a 3.3 V device rail.

Earlier TX attempts that produced no response were likely wired to the
always-streaming main-board TX line instead of the idle main-board RX line;
correct pin selection is required before any live command test.

### Live command test (Pro Micro 5 V)

A guarded Pro Micro sketch (`sniff/rovsun-promicro-tx/rovsun-promicro-tx.ino`)
confirmed bidirectional control. Wiring: Pro Micro `TX1/D1` -> main-board RX
(idle pin), `RX1/D0` -> main-board TX (streaming pin), GND common, no 5V
connection. Sending the beep-off frame `A5 01 01 21 <seq> 00 00 0F <crc>
0A 0A 00 25 00` produced:

- a `0x23` ACK frame echoing the transmitted sequence number (e.g. `A5 01 01
  23 00 70 ... 80 0A`);
- a `0x21` state report with `0C 0C` body and `00 25 00` (beep off);
- several `A5 01 00 21 ... 12 12 00 01` frames immediately after the command.

The reverse beep-on frame (`... 0A 0A 00 25 01`) produced the matching `00 25
01` report. This is the first confirmed end-to-end command: the main board
receives the command, acknowledges, and applies the setting. Captures are saved
under `captures/beep-off-test/` and `captures/beep-on-test/`.

## Phase 3 — replace the RTL8720CF with the XIAO C3

Only proceed after Phase 2 confirms `55 AA` frames and the logic voltage.
ESPHome's `tuya:` component already speaks the Tuya MCU serial protocol. You
only map the DPs discovered from the captures.

A replacement UART controller would remove the stock app/Wi-Fi module as a
competing control source. If the main MCU reports IR-originated changes over
the UART, the replacement can observe and publish those changes. It cannot
guarantee that IR and UART commands are merged or synchronized if the main
control board itself uses last-command-wins behavior; that must be verified in
the captures.

Cut the Wi-Fi module out, then connect the XIAO to the main MCU UART:

| XIAO C3 | Main MCU / module pad |
|---------|-----------------------|
| D7 GPIO20 (TX1) | main-MCU RX |
| D6 GPIO21 (RX1) | main-MCU TX |
| GND | board GND |
| 3V3 / 5V | module-power rail, only after measuring it |

Flash `esphome/rovsun-c3.yaml` over USB-C with `esphome run`.

### Files

- `docs/wifi-module-hw-analysis.md` — stock module breakout teardown and 5 V/3.3 V level-shift map
- `esphome/rovsun-c3.yaml` — replacement firmware (ESPHome Tuya MCU bridge)
- `sniff/rovsun-sniff.ino` — optional XIAO UART sniffer
- `sniff/rovsun-leonardo-sniff/rovsun-leonardo-sniff.ino` — Arduino Micro/Leonardo raw receive-only second-channel logger
- `tools/tuya-baud-detector.py` — passive host-side baud detector for one or two adapters
- `tools/a5-stream-inspector.py` — offline A5 stream splitter and sequence inspector
- `tools/rovsun-state-decoder.py` — read-only decoder for confirmed state fields in saved A5 captures
- `tools/rovsun-command-builder.py` — offline-only command template builder with CRC recalculation

## Notes and safety

- Do not inject serial commands while the stock module is connected. Two TX
  sources can cause bus contention.
- Never connect the USB-to-TTL adapter's TX or VCC during passive capture.
- Confirm the signal voltage before connecting any XIAO or adapter input. A
  multimeter showing 5 V is an idle-level measurement and does not confirm
  that the header is the main MCU UART; capture activity before replacing it.
- For the first live test, connect only the module TX receive path through the
  level shifter. Add the XIAO TX path only after the UART protocol and voltage
  are confirmed.
- The mini-split contains mains voltage. Wire only to verified low-voltage
  points, with power disconnected while wiring.
- RTL8720CF is not an ESP32. Do not assume ESP-specific flashing tools apply;
  the replacement strategy is to remove the module and speak to the main MCU
  UART.
