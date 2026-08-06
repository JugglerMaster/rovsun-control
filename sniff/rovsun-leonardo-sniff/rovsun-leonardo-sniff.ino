/*
 * Receive-only UART logger for Arduino Micro/Leonardo (ATmega32U4).
 *
 * Wiring:
 *   mini-split signal line -> board RX1 / D0
 *   mini-split signal GND  -> board GND
 *   board TX1 / D1        -> disconnected
 *   board 5V              -> disconnected
 *
 * USB logging uses Serial; the captured UART uses Serial1. USB emits the
 * captured bytes unchanged so a host-side tool can parse the stream.
 */

const unsigned long UART_BAUD = 115200;

void setup() {
  Serial.begin(115200);
  unsigned long start = millis();
  while (!Serial && millis() - start < 5000) {
    delay(10);
  }

  Serial1.begin(UART_BAUD);
}

void loop() {
  while (Serial1.available()) {
    uint8_t value = (uint8_t)Serial1.read();
    Serial.write(value);
  }
}
