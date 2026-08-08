/*
 * Guarded Pro Micro UART test controller.
 *
 * This sketch never transmits during boot. Type an exact command over USB:
 *   SEND BEEP OFF
 *   SEND BEEP ON
 *   SET 0005 06      (set register 0x0005 to 0x06, e.g. fan high)
 *
 * Wiring for a 5 V / 16 MHz ATmega32U4 Pro Micro:
 *   Pro Micro TX1 / D1 -> mini-split RX
 *   Pro Micro RX1 / D0 <- mini-split TX
 *   Pro Micro GND      -> mini-split GND
 *   Pro Micro 5V       -> disconnected
 */

const unsigned long UART_BAUD = 115200;
uint8_t commandSequence = 0x70;
String input;

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

void printHex(const uint8_t *data, size_t length) {
  for (size_t i = 0; i < length; ++i) {
    if (i) Serial.print(' ');
    if (data[i] < 0x10) Serial.print('0');
    Serial.print(data[i], HEX);
  }
  Serial.println();
}

void sendBeep(uint8_t value) {
  sendRegister(0x0025, value);
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

void setup() {
  Serial.begin(115200);
  unsigned long start = millis();
  while (!Serial && millis() - start < 5000) delay(10);
  Serial1.begin(UART_BAUD);
  Serial.println("Ready. Type SEND BEEP OFF or SEND BEEP ON.");
}

void loop() {
  while (Serial1.available()) {
    uint8_t value = (uint8_t)Serial1.read();
    if (value < 0x10) Serial.print('0');
    Serial.print(value, HEX);
    Serial.print(' ');
  }

  while (Serial.available()) {
    char value = (char)Serial.read();
    if (value == '\n' || value == '\r') {
      input.trim();
      if (input == "SEND BEEP OFF") sendBeep(0x00);
      else if (input == "SEND BEEP ON") sendBeep(0x01);
      else if (input.startsWith("SET ")) {
        // Format: SET <regHex> <valueHex>, e.g. "SET 0005 06"
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
