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
24.0 C in tenths) and register `0x0227` contained `00 00 00 4B` (75 decimal,
likely the displayed Fahrenheit value). Confirm this mapping with the reverse
temperature transition before using it for control. The reverse `75 F -> 74 F`
capture produced `0x0002 = 00 00 09 2E` (2350, plausibly 23.5 C) and
`0x0227 = 00 00 00 4A` (74), confirming both fields.

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

The app exposes additional controls that should be mapped independently:
sleep, eco, timer, fan mute, airflow direction, beep, light, generator mode,
drying, and electricity monitoring, with potentially more device-specific
options. Its fan selector has eight distinct labels: `string wind`, `high wind`,
`mid high wind`, `mid wind`, `mid low wind`, `low wind`, `mute`, and `auto`.
Both the app and IR remote can set sweep, but only the app provides independent
airflow direction control. Keep these distinctions in the capture notes;
app-only features may have UART datapoints that cannot be reproduced through the
remote.

An idle dual capture showed matching `A5 01 01 21` and `A5 01 01 23` traffic at
approximately 9.8 and 38.7 seconds, about 28.9 seconds apart, on the two
directions. Separate `A5 01 00 21`/`A5 01 00 23` frames appeared around 46.7
seconds. This is consistent with periodic status/keep-alive traffic, but more
idle captures are needed before treating 29 seconds as a fixed interval.

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

- `esphome/rovsun-c3.yaml` — replacement firmware (ESPHome Tuya MCU bridge)
- `sniff/rovsun-sniff.ino` — optional XIAO UART sniffer
- `sniff/rovsun-leonardo-sniff/rovsun-leonardo-sniff.ino` — Arduino Micro/Leonardo raw receive-only second-channel logger
- `tools/tuya-baud-detector.py` — passive host-side baud detector for one or two adapters
- `tools/a5-stream-inspector.py` — offline A5 stream splitter and sequence inspector

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
