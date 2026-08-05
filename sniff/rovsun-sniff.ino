/*
 * rovsun-sniff.ino
 * Passive serial sniffer for the Tuya MCU link on a Seeed XIAO ESP32-C3.
 *
 * Goal: confirm the baud rate and watch the 0x55 AA frames exchanged between
 * the RT9720CF module and the mini-split main board — WITHOUT cutting anything.
 *
 * Wiring (tap, do not disconnect the module):
 *   XIAO D6 (GPIO21, RX1)  ->  the MODULE's TX pad  (this is the main-MCU RX line)
 *   XIAO GND               ->  board GND
 *
 * The module's TX carries commands the module sends TO the main MCU.
 * To watch the other direction, move the wire to the MODULE's RX pad
 * (the main-MCU TX line) and re-flash / reboot.
 *
 * Open the USB Serial Monitor at 115200. Bytes are printed as hex.
 * Send a number over the monitor to change the sniff baud rate live
 * (e.g. type "9600", "19200", "115200").
 *
 * Tuya MCU frame:  55 AA <ver> <cmd> <len_hi> <len_lo> <data...> <checksum>
 *   cmd 0x00 = heartbeat, 0x01 = query, 0x02 = report (status/DPs),
 *   0x03 = set (control), 0x06 = wifi state.
 */

#include <HardwareSerial.h>

#define SNIFF_RX_PIN 21      // XIAO D6
#define SNIFF_TX_PIN 20      // XIAO D7 (unused for RX-only, left idle)
HardwareSerial Sniff(1);     // UART1 on the C3

uint32_t baud = 9600;

void setup() {
  Serial.begin(115200);
  while (!Serial) { delay(10); }
  Serial.println("Rovsun sniff bridge ready. Type a baud rate to switch.");
  startSniff(baud);
}

void startSniff(uint32_t b) {
  Sniff.end();
  Sniff.begin(b, SERIAL_8N1, SNIFF_RX_PIN, SNIFF_TX_PIN);
  Serial.printf("Sniffing at %u baud (8N1) on GPIO%d\r\n", b, SNIFF_RX_PIN);
}

void loop() {
  // Live baud change from the monitor
  if (Serial.available()) {
    String s = Serial.readStringUntil('\n');
    s.trim();
    uint32_t b = s.toInt();
    if (b >= 300 && b <= 4000000) {
      baud = b;
      startSniff(baud);
    }
  }

  // Echo every received byte as hex, with a newline on the 0x55 AA frame start
  static bool prevWas55 = false;
  while (Sniff.available()) {
    uint8_t c = Sniff.read();
    if (c == 0x55 && prevWas55) {
      Serial.println();           // new frame
      Serial.print("55 AA ");
      prevWas55 = false;
    } else if (c == 0x55) {
      prevWas55 = true;
    } else {
      prevWas55 = false;
      if (c < 0x10) Serial.print('0');
      Serial.print(c, HEX);
      Serial.print(' ');
    }
  }
}
