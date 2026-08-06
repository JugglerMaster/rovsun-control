/*
 * Receive-only UART logger for Arduino Micro/Leonardo (ATmega32U4).
 *
 * Wiring:
 *   mini-split signal line -> board RX1 / D0
 *   mini-split signal GND  -> board GND
 *   board TX1 / D1        -> disconnected
 *   board 5V              -> disconnected
 *
 * USB logging uses Serial; the captured UART uses Serial1.
 */

const unsigned long UART_BAUD = 115200;

void setup() {
  Serial.begin(115200);
  unsigned long start = millis();
  while (!Serial && millis() - start < 5000) {
    delay(10);
  }

  Serial1.begin(UART_BAUD);
  Serial.println("Rovsun Leonardo receive-only logger");
  Serial.println("UART: Serial1 RX=D0, 115200 8N1; TX=D1 unused");
}

void loop() {
  static unsigned long lastByte = 0;
  static bool haveBytes = false;

  while (Serial1.available()) {
    if (!haveBytes || millis() - lastByte > 20) {
      if (haveBytes) Serial.println();
      Serial.print(millis());
      Serial.print(" ms: ");
      haveBytes = true;
    }

    uint8_t value = (uint8_t)Serial1.read();
    if (value < 0x10) Serial.print('0');
    Serial.print(value, HEX);
    Serial.print(' ');
    lastByte = millis();
  }
}
