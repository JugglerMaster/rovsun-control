#pragma once

#include <vector>
#include <string>
#include "esphome/core/component.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/switch/switch.h"
#include "esphome/components/select/select.h"
#include "esphome/components/number/number.h"

namespace esphome {
namespace rovsun_a5 {

class RovsunA5 : public Component, public uart::UARTDevice {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;

  void set_power_switch(switch_::Switch *s) { power_switch_ = s; }
  void set_beep_switch(switch_::Switch *s) { beep_switch_ = s; }
  void set_fan_select(select::Select *s) { fan_select_ = s; }
  void set_vdir_select(select::Select *s) { vdir_select_ = s; }
  void set_mode_select(select::Select *s) { mode_select_ = s; }
  void set_setpoint_number(number::Number *s) { setpoint_number_ = s; }

  // Called from YAML lambdas when the user changes an entity.
  void control_power(bool on);
  void control_beep(bool on);
  void control_fan(uint8_t val);
  void control_vdir(uint8_t val);
  void control_mode(uint8_t val);
  void control_setpoint(float celsius);

 private:
  void process_();
  void parse_frame_(const uint8_t *frame, size_t len);
  void apply_register_(uint16_t reg, uint32_t value);
  void send_register_(uint16_t reg, const std::vector<uint8_t> &value);
  static uint16_t crc16_xmodem_(const uint8_t *data, size_t len);

  switch_::Switch *power_switch_{nullptr};
  switch_::Switch *beep_switch_{nullptr};
  select::Select *fan_select_{nullptr};
  select::Select *vdir_select_{nullptr};
  select::Select *mode_select_{nullptr};
  number::Number *setpoint_number_{nullptr};

  std::vector<uint8_t> rx_;
  uint8_t seq_ = 0x70;
};

}  // namespace rovsun_a5
}  // namespace esphome
