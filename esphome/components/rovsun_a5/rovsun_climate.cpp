#include "rovsun_climate.h"
#include "esphome/core/log.h"

namespace esphome {
namespace rovsun_a5 {

static const char *TAG = "rovsun_a5.climate";

static climate::ClimateMode mode_code_to_climate(uint8_t v) {
  switch (v) {
    case 1: return climate::CLIMATE_MODE_COOL;
    case 2: return climate::CLIMATE_MODE_DRY;
    case 3: return climate::CLIMATE_MODE_FAN_ONLY;
    case 4: return climate::CLIMATE_MODE_HEAT;
    default: return climate::CLIMATE_MODE_AUTO;
  }
}

static uint8_t climate_mode_to_code(climate::ClimateMode m) {
  switch (m) {
    case climate::CLIMATE_MODE_COOL: return 1;
    case climate::CLIMATE_MODE_DRY: return 2;
    case climate::CLIMATE_MODE_FAN_ONLY: return 3;
    case climate::CLIMATE_MODE_HEAT: return 4;
    default: return 0;  // auto
  }
}

static uint8_t fan_to_code(const std::string &s) {
  if (s == "mute") return 1;
  if (s == "low_wind") return 2;
  if (s == "mid_low_wind") return 3;
  if (s == "mid_wind") return 4;
  if (s == "mid_high_wind") return 5;
  if (s == "high_wind") return 6;
  if (s == "strong_wind") return 7;
  return 0;  // auto
}

static uint8_t vdir_to_code(const std::string &s) {
  if (s == "up") return 2;
  if (s == "down") return 3;
  if (s == "up_fix") return 9;
  if (s == "above_fix") return 0x0A;
  if (s == "middle_fix") return 0x0B;
  if (s == "above_down_fix") return 0x0C;
  if (s == "down_fix") return 0x0D;
  return 1;  // flow
}

void RovsunClimate::setup() {
  // Sane defaults until the first 0x21 report arrives from the main board.
  this->target_temperature = 22;
  this->mode = climate::CLIMATE_MODE_OFF;
  this->fan_mode = "auto";
  this->swing_mode = "flow";
  this->publish_state();
}

climate::ClimateTraits RovsunClimate::traits() {
  auto t = climate::ClimateTraits();
  t.set_supports_current_temperature(false);
  t.set_supported_modes({
      climate::CLIMATE_MODE_OFF,
      climate::CLIMATE_MODE_AUTO,
      climate::CLIMATE_MODE_COOL,
      climate::CLIMATE_MODE_DRY,
      climate::CLIMATE_MODE_FAN_ONLY,
      climate::CLIMATE_MODE_HEAT,
  });
  t.set_supported_fan_modes({
      "auto", "mute", "low_wind", "mid_low_wind", "mid_wind",
      "mid_high_wind", "high_wind", "strong_wind",
  });
  t.set_supported_swing_modes({
      "flow", "up", "down", "up_fix", "above_fix", "middle_fix",
      "above_down_fix", "down_fix",
  });
  t.set_visual_min_temperature(16);
  t.set_visual_max_temperature(30);
  t.set_visual_target_temperature_step(0.5);
  return t;
}

void RovsunClimate::control(const climate::ClimateCall &call) {
  if (call.get_mode().has_value()) {
    climate::ClimateMode m = *call.get_mode();
    if (m == climate::CLIMATE_MODE_OFF) {
      this->mode = m;
      this->publish_state();  // optimistic; report will confirm
      parent_->control_power(false);
    } else {
      this->mode = m;
      this->publish_state();
      parent_->control_power(true);
      parent_->control_mode(climate_mode_to_code(m));
    }
  }
  if (call.get_fan_mode().has_value()) {
    this->fan_mode = *call.get_fan_mode();
    this->publish_state();
    parent_->control_fan(fan_to_code(*call.get_fan_mode()));
  }
  if (call.get_swing_mode().has_value()) {
    this->swing_mode = *call.get_swing_mode();
    this->publish_state();
    parent_->control_vdir(vdir_to_code(*call.get_swing_mode()));
  }
  if (call.get_target_temperature().has_value()) {
    this->target_temperature = *call.get_target_temperature();
    this->publish_state();
    parent_->control_setpoint(*call.get_target_temperature());
  }
}

}  // namespace rovsun_a5
}  // namespace esphome
