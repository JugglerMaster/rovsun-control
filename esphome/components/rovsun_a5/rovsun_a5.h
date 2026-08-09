#pragma once

#include <vector>
#include <string>
#include "esphome/core/component.h"
#include "esphome/components/uart/uart.h"
#include "esphome/components/switch/switch.h"
#include "esphome/components/select/select.h"
#include "esphome/components/climate/climate.h"

namespace esphome {
namespace rovsun_a5 {

class RovsunClimate;  // forward

class RovsunA5 : public Component, public uart::UARTDevice {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;

  void set_climate(RovsunClimate *c) { climate_ = c; }
  void set_power_switch(switch_::Switch *s) { power_switch_ = s; }
  void set_beep_switch(switch_::Switch *s) { beep_switch_ = s; }
  void set_light_switch(switch_::Switch *s) { light_switch_ = s; }
  void set_drying_switch(switch_::Switch *s) { drying_switch_ = s; }
  void set_sleep_select(select::Select *s) { sleep_select_ = s; }
  void set_eco_select(select::Select *s) { eco_select_ = s; }
  void set_generator_select(select::Select *s) { generator_select_ = s; }
  void set_lrdir_select(select::Select *s) { lrdir_select_ = s; }
  void set_vdir_select(select::Select *s) { vdir_select_ = s; }
  void set_log_raw(bool b) { log_raw_ = b; }
  void set_restore_on_power_on(bool b) { restore_on_power_on_ = b; }

  // Called from YAML lambdas / climate when the user changes an entity.
  void control_power(bool on);
  void control_beep(bool on);
  void control_fan(uint8_t val);
  void control_vdir(uint8_t val);
  void control_mode(uint8_t val);
  void control_setpoint(float celsius);
  void control_light(bool on);
  void control_drying(bool on);
  void control_sleep(uint8_t val);
  void control_eco(uint8_t val);
  void control_generator(uint8_t val);
  void control_lrdir(uint8_t val);

 private:
  void process_();
  void parse_frame_(const uint8_t *frame, size_t len);
  void apply_register_(uint16_t reg, uint32_t value);
  void update_climate_();
  void restore_settings_();
  static climate::ClimateMode mode_code_to_climate_(uint8_t v);
  void send_register_(uint16_t reg, const std::vector<uint8_t> &value);
  void log_frame_(const char *dir, const uint8_t *data, size_t len);
  static uint16_t crc16_xmodem_(const uint8_t *data, size_t len);

  switch_::Switch *power_switch_{nullptr};
  switch_::Switch *beep_switch_{nullptr};
  switch_::Switch *light_switch_{nullptr};
  switch_::Switch *drying_switch_{nullptr};
  select::Select *sleep_select_{nullptr};
  select::Select *eco_select_{nullptr};
  select::Select *generator_select_{nullptr};
  select::Select *lrdir_select_{nullptr};
  select::Select *vdir_select_{nullptr};
  RovsunClimate *climate_{nullptr};

  bool log_raw_{false};
  bool restore_on_power_on_{true};
  bool power_on_{false};
  bool seen_any_{false};
  uint8_t mode_{0};
  uint8_t fan_{0};
  uint8_t vdir_{1};
  uint8_t lrdir_{0};
  uint32_t setpoint_{0};

  // Last values commanded through ESPHome, replayed on power-on so the unit
  // matches HA's desired state after a power loss or IR-originated power-on.
  // 0xFF is a sentinel meaning "never commanded / do not replay".
  uint8_t cmd_fan_{0xFF};
  uint8_t cmd_vdir_{0xFF};
  uint8_t cmd_mode_{0xFF};
  uint32_t cmd_setpoint_{0};
  uint8_t cmd_beep_{0xFF};
  uint8_t cmd_light_{0xFF};
  uint8_t cmd_drying_{0xFF};
  uint8_t cmd_sleep_{0xFF};
  uint8_t cmd_eco_{0xFF};
  uint8_t cmd_gen_{0xFF};
  uint8_t gen_state_{0xFF};  // last generator value reported by the AC (0x21)
  uint8_t cmd_lrdir_{0xFF};

  std::vector<uint8_t> rx_;
  uint8_t seq_ = 0x70;
};

}  // namespace rovsun_a5
}  // namespace esphome
