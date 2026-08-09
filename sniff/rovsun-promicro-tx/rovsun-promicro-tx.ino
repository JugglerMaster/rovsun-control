/*
 * Rovsun A5 bus monitor + guarded sender for a 5 V / 16 MHz ATmega32U4 Pro Micro.
 *
 * Two roles:
 *  - PASSIVE MONITOR (default): every byte received on Serial1 (RX1 / D0) is
 *    parsed into A5 frames, CRC-checked, and printed to USB so you can watch
 *    the ESP32 (XIAO C6) issue commands in response to Home Assistant.
 *  - GUARDED SENDER: type a command over USB (e.g. "SEND BEEP ON") to transmit
 *    an A5 frame on Serial1.
 *
 * ---------------------------------------------------------------------------
 * WIRING TO WATCH THE ESP32 (safe one-way tap -- leave Pro Micro TX DISCONNECTED)
 * ---------------------------------------------------------------------------
 * The XIAO C6 config uses D7 = GPIO17 for TX. Tap that line:
 *   ESP32 D7 (GPIO17, TX) -> Pro Micro RX1 / D0
 *   ESP32 GND             -> Pro Micro GND
 *   Pro Micro TX1 / D1    -> NOT CONNECTED (never drive the live bus)
 *
 * Open the USB Serial Monitor at 115200. Operate the unit from HA (toggle a
 * switch, change setpoint, etc.) and you should see framed `A5 01 01 21 ... 0A 0A`
 * lines with "crc=ok". To also watch the unit's replies, move the Pro Micro RX
 * wire to ESP32 D6 (GPIO16, RX) and reboot -- those arrive as `0C 0C` frames.
 *
 * ---------------------------------------------------------------------------
 * WIRING TO SEND A TEST (bench only -- ESP32 and/or mini-split removed from bus)
 * ---------------------------------------------------------------------------
 *   Pro Micro TX1 / D1 -> mini-split RX
 *   Pro Micro RX1 / D0 <- mini-split TX
 *   Pro Micro GND      -> mini-split GND
 *   Pro Micro 5V       -> disconnected
 *
 * WARNING: never type a SEND command while the Pro Micro TX is wired to a live
 * bus that also has the ESP32 attached -- two TX sources cause bus contention and
 * can corrupt the link the ESP32 relies on.
 */

const unsigned long UART_BAUD = 115200;
uint8_t commandSequence = 0x70;
String input;

// Receive buffer for frame-aligned parsing.
const int BUF_MAX = 512;
uint8_t buf[BUF_MAX];
int bufLen = 0;

uint16_t crc16Xmodem(const uint8_t *data, size_t length) {
  uint16_t crc = 0;
  while (length--) {
    crc ^= (uint16_t)*data++ << 8;
    for (uint8_t bit = 0; bit < 8; ++bit) {
      crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
    }
  }
  return crc;
}

// CRC helper that folds one byte at a time (keeps the parser branch-free).
uint16_t crc16XmodemByte(uint16_t crc, uint8_t value) {
  crc ^= (uint16_t)value << 8;
  for (uint8_t bit = 0; bit < 8; ++bit) {
    crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
  }
  return crc;
}

void printHex(const uint8_t *data, size_t length) {
  for (size_t i = 0; i < length; ++i) {
    if (i) Serial.print(' ');
    if (data[i] < 0x10) Serial.print('0');
    Serial.print(data[i], HEX);
  }
}

void sendBeep(uint8_t value) {
  sendRegister(0x0025, value);
}

// Send a synthetic STATE REPORT (0x21, 0C 0C) the ESP32 will parse and publish.
// On first contact this triggers the ESP32's restore-on-power-on replay, which
// makes it TRANSMIT a burst of command frames back out its TX -- a loopback that
// proves the whole Pro Micro <-> ESP32 path without needing Home Assistant.
void sendReport(uint16_t reg, uint8_t value) {
  uint8_t frame[15];
  frame[0] = 0xA5; frame[1] = 0x01; frame[2] = 0x01; frame[3] = 0x21;
  frame[4] = commandSequence++; frame[5] = 0x00; frame[6] = 0x00;
  frame[7] = (uint8_t)sizeof(frame);   // total frame length (15)
  frame[8] = 0x00; frame[9] = 0x00;    // CRC filled below
  frame[10] = 0x0C; frame[11] = 0x0C;  // report body prefix
  frame[12] = (uint8_t)(reg >> 8); frame[13] = (uint8_t)(reg & 0xFF); frame[14] = value;

  uint8_t crcInput[13];
  memcpy(crcInput, frame, 8);
  memcpy(crcInput + 8, frame + 10, 5);
  uint16_t crc = crc16Xmodem(crcInput, sizeof(crcInput));
  frame[8] = crc >> 8; frame[9] = crc & 0xFF;

  Serial.print("TX(report) ");
  printHex(frame, sizeof(frame));
  Serial1.write(frame, sizeof(frame));
  Serial1.flush();
}

void sendRegister(uint16_t reg, uint8_t value) {
  uint8_t frame[] = {
      0xA5, 0x01, 0x01, 0x21, commandSequence++, 0x00, 0x00, 0x0F,
      0x00, 0x00, 0x0A, 0x0A,
      (uint8_t)(reg >> 8), (uint8_t)(reg & 0xFF), value};
  // Calculate over both sections in one pass to avoid including the CRC.
  uint8_t crcInput[13];
  memcpy(crcInput, frame, 8);
  memcpy(crcInput + 8, frame + 10, 5);
  uint16_t crc = crc16Xmodem(crcInput, sizeof(crcInput));
  frame[8] = crc >> 8;
  frame[9] = crc & 0xFF;

  Serial.print("TX ");
  printHex(frame, sizeof(frame));
  Serial1.write(frame, sizeof(frame));
  Serial1.flush();
}

// Parse and pretty-print one complete frame (len = byte 7 = total frame length).
void printFrame(const uint8_t *frame, uint8_t len) {
  uint16_t expected = ((uint16_t)frame[8] << 8) | frame[9];
  uint16_t actual = crc16Xmodem(frame, 8);
  // CRC runs over header (8) + everything after the 2 CRC bytes.
  for (uint8_t i = 10; i < len; ++i) actual = crc16XmodemByte(actual, frame[i]);
  bool crcOk = (expected == actual);

  Serial.println();
  Serial.print("A5 frame: ");
  printHex(frame, len);
  Serial.println();

  const char *kind = "?";
  if (frame[3] == 0x21 && frame[10] == 0x0A && frame[11] == 0x0A) kind = "CMD";
  else if (frame[3] == 0x21 && frame[10] == 0x0C && frame[11] == 0x0C) kind = "RPT";
  else if (frame[3] == 0x23) kind = "ACK";

  uint8_t seq = (frame[4] != 0) ? frame[4] : frame[5];
  Serial.print("  kind=");
  Serial.print(kind);
  Serial.print(" cmd=0x");
  Serial.print(frame[3], HEX);
  Serial.print(" seq=0x");
  Serial.print(seq, HEX);
  Serial.print(" len=");
  Serial.print(len);
  Serial.print(" crc=");
  Serial.println(crcOk ? "ok" : "BAD");

  // For command/report frames, decode register writes as (addr:2, value:1) records.
  if (len >= 12) {
    Serial.print("  body: ");
    printHex(frame + 10, len - 10);
    Serial.println();
    if ((frame[10] == 0x0A || frame[10] == 0x0C) && (len - 12) % 3 == 0 && (len - 12) > 0) {
      Serial.print("  regs:");
      for (uint8_t i = 12; i + 3 <= len; i += 3) {
        uint16_t reg = ((uint16_t)frame[i] << 8) | frame[i + 1];
        Serial.print(" 0x");
        if (reg < 0x1000) Serial.print('0');
        if (reg < 0x0100) Serial.print('0');
        if (reg < 0x0010) Serial.print('0');
        Serial.print(reg, HEX);
        Serial.print("=0x");
        if (frame[i + 2] < 0x10) Serial.print('0');
        Serial.print(frame[i + 2], HEX);
      }
      Serial.println();
    }
  }
}

void processBuffer() {
  int i = 0;
  while (i + 8 <= bufLen) {
    if (buf[i] != 0xA5) { ++i; continue; }
    uint8_t len = buf[i + 7];
    if (len < 12) { ++i; continue; }
    if (i + len > bufLen) break;  // frame not fully arrived yet
    printFrame(buf + i, len);
    i += len;
  }
  if (i > 0) {
    memmove(buf, buf + i, bufLen - i);
    bufLen -= i;
  }
  // Desync guard: if the buffer is nearly full with no parse progress, drop it.
  if (bufLen > BUF_MAX - 64) bufLen = 0;
}

void setup() {
  Serial.begin(115200);
  unsigned long start = millis();
  while (!Serial && millis() - start < 5000) delay(10);
  Serial1.begin(UART_BAUD);
  Serial.println("Rovsun A5 monitor ready. Wired as a one-way tap? Just watch.");
  Serial.println("Type SEND BEEP OFF / SEND BEEP ON / SET <reg> <val> to transmit (bench only!).");
}

void loop() {
  while (Serial1.available()) {
    if (bufLen < BUF_MAX) buf[bufLen++] = (uint8_t)Serial1.read();
  }
  if (bufLen > 0) processBuffer();

  while (Serial.available()) {
    char value = (char)Serial.read();
    if (value == '\n' || value == '\r') {
      input.trim();
      if (input == "SEND BEEP OFF") sendBeep(0x00);
      else if (input == "SEND BEEP ON") sendBeep(0x01);
      else if (input == "REPORT") sendReport(0x0001, 0x01);
      else if (input.startsWith("SET ")) {
        int sp = input.indexOf(' ', 4);
        if (sp > 4) {
          uint16_t reg = (uint16_t)strtol(input.substring(4, sp).c_str(), NULL, 16);
          uint8_t val = (uint8_t)strtol(input.substring(sp + 1).c_str(), NULL, 16);
          sendRegister(reg, val);
        } else {
          Serial.println("Ignored. Use: SET <regHex> <valueHex>");
        }
      }
      else if (input.length()) Serial.println("Ignored. Exact command required.");
      input = "";
    } else if (input.length() < 32) {
      input += value;
    }
  }
}
