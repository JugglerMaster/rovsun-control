# WiFi Module Hardware Reverse Engineering

> Source: manual analysis of the Tuya-compatible WiFi module breakout board and
> its datasheet (TCLWBR WiFi + Bluetooth module). Notes for helping the protocol
> agent understand the physical interface before UART capture.

## The "Aha!" Moment: The Context

The datasheet tells us exactly what this is: The TCLWBR is a Tuya WiFi + Bluetooth
module.

- **Crucial fact:** The module operates on 5V (Pin 1: 5V).
- **The problem:** Most modern microcontrollers (ESP32, STM32, Raspberry Pi, etc.)
  operate on 3.3V logic.
- **The solution:** This PCB is a breakout/interface board specifically designed to
  allow a 3.3V microcontroller to "talk" to this 5V WiFi module without burning out
  the microcontroller.

## Mapping the Components (Q1, Q2, Q3)

Based on the datasheet (which shows a single TX/RX pair) and the observed
asymmetric circuit, here is the logical map of those components.

### The TX Path (3.3V → 5V "Up-shifting")

Since the module is 5V, the 3.3V microcontroller needs to send a HIGH signal that
reaches 5V. A simple resistor divider can't do this (it can only go down), so a
transistor is used to "switch" the 5V line.

- **Q1 (Top transistor): The TX driver.** Acts as a gate. When the 3.3V controller
  sends LOW (0V), it turns the transistor on, pulling the 5V TX line to ground.
  When the controller sends HIGH (3.3V), it turns the transistor off, allowing a
  pull-up resistor to pull the line up to 5V. This is the transistor for the TX pin.

### The RX Path (5V → 3.3V "Down-shifting")

The module's TX sends 5V signals back to the 3.3V controller. To prevent damage, the
voltage must be stepped down.

- **Resistor divider (R1 & R2):** Two resistors in series split the 5V into a 3.3V
  signal. This is why there is no transistor on the RX line.

### The "Mystery" Transistors (Q2 and Q3)

Since the datasheet only mentions one TX/RX pair, why are there two more transistors?

- **Possibility A (Extra signals):** Most Tuya modules have a Reset (RST) pin and an
  Enable (EN/PWDN) pin to wake the module from sleep. Even if not in the datasheet
  snippet, these pins are almost always present on the physical module. Q2 and Q3 are
  likely level shifters for the Reset and Enable lines.
- **Possibility B (Multi-channel):** If this is a generic breakout board, it might be
  designed to handle multiple UART interfaces, but Possibility A is far more common.

## Summary Map

| Component | Function               | Signal Direction                | Logic Shift                |
|-----------|------------------------|--------------------------------|----------------------------|
| Q1        | TX level shifter       | 3.3V (MCU) → 5V (Module)       | Up-shift (transistor switch)|
| Q2        | Signal shifter         | (Likely Reset/Enable)          | Up-shift (transistor switch)|
| Q3        | Signal shifter         | (Likely Reset/Enable)          | Up-shift (transistor switch)|
| R1 + R2   | RX level shifter       | 5V (Module) → 3.3V (MCU)       | Down-shift (resistor divider)|

## Final Warning for the Project

- **Powering the module:** You MUST provide 5V to Pin 1 (the 5V input). If you power
  the module with 3.3V, WiFi will never connect (datasheet requires 4.5V–5.5V).
- **The 5V → 3.3V transition:** Because the RX line uses a resistor divider, it is a
  passive shifter. It is perfect for UART, but will fail for high-speed signals like
  SPI or high-speed I2C. For standard serial (UART) it is exactly what is needed.
