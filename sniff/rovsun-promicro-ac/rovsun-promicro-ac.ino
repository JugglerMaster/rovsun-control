// Rovsun Pro Micro AC-emulator / capture bridge (ATmega32U4, USB-C).
//
// Pretends to be the AC main board so the Tuya (RTL8720CF) module establishes
// its MCU link (app then enables controls) and relays every app command as an
// A5 0x21 0A0A frame we capture.
//
// WIRING:
//   Tuya module TX  -> Pro Micro RX1 (D0)
//   Pro Micro TX1 (D1) -> Tuya module RX   (must be connected so we can answer)
//   Tuya GND         <-> Pro Micro GND
//   Tuya 5V          <- external 5V supply
//   USB              -> PC (console, native USB CDC, no FTDI needed)
//
// Bus framing: 115200 8N1. Frame: A5 01 <b2> <cmd> <seq> 00 00 <len> <crc16>
//              <body...>. CRC-16/XMODEM over header(8) + body.

#include <string.h>

#define BUS Serial1                       // hardware UART to the module
const unsigned long BUS_BAUD = 115200;
const unsigned long CONSOLE_BAUD = 115200;

const unsigned long REPORT_INTERVAL = 10000;
const unsigned long QUERY_INTERVAL  = 20000;

bool emulate = true;
uint8_t reportSeq = 0x01;

const uint8_t Q_11[] = {0xA5,0x01,0x00,0x21,0x00,0x00,0x00,0x0C,0x65,0xCE,0x11,0x11};
const uint8_t Q_10[] = {0xA5,0x01,0x00,0x21,0x00,0x00,0x00,0x0C,0x46,0xDE,0x10,0x10};
const uint8_t Q_26[] = {0xA5,0x01,0x00,0x21,0x00,0x00,0x00,0x0C,0xBF,0x78,0x26,0x26};

// Captured AC cold-start metadata response. Total length is 0xD3 (211 bytes).
const uint8_t STARTUP_METADATA[] = {
  0xA5, 0x01, 0x00, 0x23, 0x00, 0x01, 0x00, 0xD3, 0xFB, 0x1F, 0x80, 0x00,
  0x01, 0x70, 0x6B, 0x00, 0x10, 0x6E, 0x6E, 0x32, 0x6F, 0x6F, 0x61, 0x61,
  0x63, 0x73, 0x77, 0x7A, 0x36, 0x75, 0x79, 0x69, 0x30, 0x70, 0x73, 0x00,
  0x10, 0x6E, 0x6E, 0x32, 0x6F, 0x6F, 0x61, 0x61, 0x63, 0x73, 0x77, 0x7A,
  0x36, 0x75, 0x79, 0x69, 0x30, 0x76, 0x73, 0x00, 0x4B, 0x7B, 0x22, 0x4D,
  0x43, 0x55, 0x22, 0x3A, 0x5B, 0x22, 0x41, 0x43, 0x4D, 0x43, 0x55, 0x2F,
  0x56, 0x39, 0x2D, 0x52, 0x31, 0x30, 0x46, 0x54, 0x32, 0x37, 0x41, 0x43,
  0x2D, 0x46, 0x56, 0x30, 0x30, 0x31, 0x2E, 0x30, 0x30, 0x31, 0x2E, 0x30,
  0x33, 0x30, 0x22, 0x5D, 0x2C, 0x22, 0x53, 0x4E, 0x22, 0x3A, 0x22, 0x31,
  0x31, 0x31, 0x32, 0x30, 0x31, 0x58, 0x58, 0x58, 0x58, 0x58, 0x58, 0x58,
  0x58, 0x58, 0x58, 0x58, 0x58, 0x58, 0x58, 0x58, 0x58, 0x58, 0x22, 0x7D,
  0x73, 0x72, 0x00, 0x03, 0x61, 0x70, 0x70, 0x73, 0x64, 0x00, 0x10, 0x74,
  0x63, 0x6C, 0x5F, 0x41, 0x43, 0x5F, 0x74, 0x2A, 0x61, 0x70, 0x5F, 0x73,
  0x7A, 0x6B, 0x74, 0x70, 0x77, 0x00, 0x20, 0x62, 0x5C, 0x66, 0x79, 0x68,
  0x44, 0x42, 0x6D, 0x39, 0x6B, 0x66, 0x5C, 0x66, 0x6F, 0x43, 0x56, 0x62,
  0x24, 0x45, 0x56, 0x53, 0x42, 0x2C, 0x75, 0x62, 0x55, 0x4C, 0x56, 0x6E,
  0x5F, 0x35, 0x46, 0x6D, 0x74, 0x00, 0x04, 0x00, 0x00, 0x00, 0xC8, 0x6D,
  0x6C, 0x00, 0x04, 0x00, 0x00, 0xFF, 0xFF
};

const uint8_t REPORT_BODY[56] = {
  0x0C,0x0C, 0x00,0x01,0x01,0x00, 0x02,0x00,0x00,0x0A, 0x28,0x00,
  0x03,0x00,0x00,0x09, 0xA6,0x00, 0x05,0x00,0x00,0x0C, 0x00,0x00,
  0x0D,0x00,0x00,0x0E, 0x08,0x00, 0x11,0x08, 0x00,0x12, 0x01,0x00,
  0xDF,0x00,0x00,0xC9, 0x00,0x00, 0x17,0x00,0x00,0x1E, 0x01,0x02,
  0x27,0x00,0x00,0x00, 0x4F,0x01, 0x48,0x01
};

uint8_t rxBuf[256];
uint8_t rxLen = 0;
String line;

uint16_t crc16(const uint8_t *d, size_t n) {
  uint16_t c = 0;
  while (n--) {
    c ^= (uint16_t)(*d++) << 8;
    for (uint8_t b = 0; b < 8; b++)
      c = (c & 0x8000) ? (uint16_t)((c << 1) ^ 0x1021) : (uint16_t)(c << 1);
  }
  return c;
}

void printHex(const uint8_t *d, uint8_t n) {
  for (uint8_t i = 0; i < n; i++) {
    if (i) Serial.print(' ');
    if (d[i] < 0x10) Serial.print('0');
    Serial.print(d[i], HEX);
  }
}

void sendFrame(uint8_t b2, uint8_t cmd, uint8_t seq, const uint8_t *body, uint8_t bodyLen) {
  uint8_t f[80];
  uint8_t total = 10 + bodyLen;
  f[0] = 0xA5; f[1] = 0x01; f[2] = b2; f[3] = cmd; f[4] = seq;
  f[5] = 0x00; f[6] = 0x00; f[7] = total; f[8] = 0x00; f[9] = 0x00;
  for (uint8_t i = 0; i < bodyLen; i++) f[10 + i] = body[i];
  uint8_t cb[80];
  memcpy(cb, f, 8);
  memcpy(cb + 8, f + 10, bodyLen);
  uint16_t c = crc16(cb, 8 + bodyLen);
  f[8] = c >> 8; f[9] = c & 0xFF;
  BUS.write(f, total);
  Serial.print("[TX] ");
  printHex(f, total);
  Serial.println();
}

// AC ack the module expects (0x23, 80 0A); echoed seq in byte 5.
void sendAck(uint8_t seq) {
  uint8_t f[12] = {0xA5, 0x01, 0x01, 0x23, 0x00, seq, 0x00, 0x0C, 0x00, 0x00, 0x80, 0x0A};
  uint8_t cb[10];
  memcpy(cb, f, 8);
  cb[8] = 0x80; cb[9] = 0x0A;
  uint16_t c = crc16(cb, 10);
  f[8] = c >> 8; f[9] = c & 0xFF;
  BUS.write(f, 12);
  Serial.print("[TX] ");
  printHex(f, 12);
  Serial.println();
}

void sendQueries() {
  BUS.write(Q_11, sizeof(Q_11));
  Serial.print("[TX] "); printHex(Q_11, sizeof(Q_11)); Serial.println();
  BUS.write(Q_10, sizeof(Q_10));
  Serial.print("[TX] "); printHex(Q_10, sizeof(Q_10)); Serial.println();
  BUS.write(Q_26, sizeof(Q_26));
  Serial.print("[TX] "); printHex(Q_26, sizeof(Q_26)); Serial.println();
}

void sendStartupMetadata() {
  BUS.write(STARTUP_METADATA, sizeof(STARTUP_METADATA));
  Serial.print("[TX] ");
  printHex(STARTUP_METADATA, sizeof(STARTUP_METADATA));
  Serial.println();
}

void sendReport() {
  sendFrame(0x01, 0x21, reportSeq++, REPORT_BODY, sizeof(REPORT_BODY));
}

void replay(String hex) {
  hex.replace("0x", ""); hex.replace("0X", ""); hex.replace(" ", "");
  int n = hex.length() / 2;
  if (n <= 0 || n > 200) { Serial.println("? bad hex"); return; }
  uint8_t buf[200];
  for (int k = 0; k < n; k++)
    buf[k] = (uint8_t)strtol(hex.substring(2 * k, 2 * k + 2).c_str(), NULL, 16);
  BUS.write(buf, n);
  Serial.print("[TX] ");
  printHex(buf, n);
  Serial.println();
}

void processFrame(uint8_t *f, uint8_t len) {
  uint8_t cb[260];
  memcpy(cb, f, 8);
  memcpy(cb + 8, f + 10, len - 10);
  uint16_t exp = ((uint16_t)f[8] << 8) | f[9];
  bool ok = (crc16(cb, 8 + (len - 10)) == exp);

  Serial.print("[RX] ");
  printHex(f, len);
  Serial.println();
  Serial.print("  crc=");
  Serial.print(ok ? "ok" : "BAD");
  Serial.print(" cmd=0x");
  Serial.print(f[3], HEX);
  Serial.print(" seq=0x");
  Serial.print(f[4], HEX);

  uint8_t p0 = f[10], p1 = f[11];
  if (p0 == 0x0A || p0 == 0x0C || p0 == 0x11 || p0 == 0x10 || p0 == 0x26) {
    Serial.print(" pre=");
    Serial.print(p0, HEX);
    Serial.print(p1, HEX);
    Serial.print(" regs:");
    for (uint8_t k = 12; k + 3 <= len; k += 3) {
      uint16_t reg = ((uint16_t)f[k] << 8) | f[k + 1];
      Serial.print(" 0x");
      if (reg < 0x1000) Serial.print('0');
      if (reg < 0x0100) Serial.print('0');
      if (reg < 0x0010) Serial.print('0');
      Serial.print(reg, HEX);
      Serial.print("=0x");
      if (f[k + 2] < 0x10) Serial.print('0');
      Serial.print(f[k + 2], HEX);
    }
  }
  Serial.println();

  if (emulate && ok && f[3] == 0x21) {
    if (p0 == 0x0A && p1 == 0x0A) {
      sendAck(f[4]);            // module command -> AC acknowledges (echo seq)
    } else if (p0 == 0x00 && p1 == 0x00) {
      sendReport();             // module query -> AC answers with a state report
    } else {
      sendAck(f[4]);            // anything else -> ACK so it sees a live AC
    }
  }
}

void handleBus() {
  while (BUS.available()) {
    if (rxLen < 256) rxBuf[rxLen++] = (uint8_t)BUS.read();
  }
  uint8_t i = 0;
  while (i + 8 <= rxLen) {
    if (rxBuf[i] != 0xA5 || rxBuf[i + 1] != 0x01 ||
        (rxBuf[i + 2] != 0x00 && rxBuf[i + 2] != 0x01)) { i++; continue; }
    uint8_t len = rxBuf[i + 7];
    if (len < 10) { i++; continue; }
    if (i + len > rxLen) break;
    processFrame(rxBuf + i, len);
    i += len;
  }
  if (i > 0) { memmove(rxBuf, rxBuf + i, rxLen - i); rxLen -= i; }
  if (rxLen > 200) rxLen = 0;
}

void handleConsole() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      line.trim();
      if (line.length()) {
        if (line == "HELP") {
          Serial.println("HELP: MODE SNIFF | MODE EMULATE | QUERY | REPORT | REPLAY <hex> | STATUS");
        } else if (line == "MODE SNIFF") {
          emulate = false; Serial.println("mode=SNIFF (listen only)");
        } else if (line == "MODE EMULATE") {
          emulate = true; Serial.println("mode=EMULATE");
        } else if (line == "QUERY") {
          sendQueries();
        } else if (line == "REPORT") {
          sendReport();
        } else if (line.startsWith("REPLAY ")) {
          replay(line.substring(7));
        } else if (line == "STATUS") {
          Serial.print("emulate="); Serial.print(emulate ? "on" : "off");
          Serial.print(" reportSeq=0x"); Serial.println(reportSeq, HEX);
        } else {
          Serial.println("? unknown (HELP)");
        }
      }
      line = "";
    } else if (line.length() < 80) {
      line += c;
    }
  }
}

unsigned long lastReport = 0;
unsigned long lastQuery = 0;
bool startupMetadataSent = false;

void setup() {
  Serial.begin(CONSOLE_BAUD);
  BUS.begin(BUS_BAUD);
  Serial.println("Rovsun Pro Micro AC-emulator / capture bridge ready.");
  Serial.println("Tuya TX->D0, D1->Tuya RX, GND common, module 5V supplied. USB = console.");
  Serial.println("Commands: HELP MODE QUERY REPORT REPLAY");
  if (emulate) {
    sendQueries();
    sendReport();
    lastQuery = millis();
    lastReport = millis();
  }
}

void loop() {
  handleBus();
  handleConsole();
  if (emulate) {
    unsigned long now = millis();
    if (!startupMetadataSent && now >= 7000) {
      sendStartupMetadata();
      startupMetadataSent = true;
    }
    if (now - lastQuery >= QUERY_INTERVAL) { sendQueries(); lastQuery = now; }
    if (now - lastReport >= REPORT_INTERVAL) { sendReport(); lastReport = now; }
  }
}
