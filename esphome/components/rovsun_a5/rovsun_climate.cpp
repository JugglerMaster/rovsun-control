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

RovsunClimate::RovsunClimate() {
  this->target_temperature = 25.0f;  // 77 F default until the AC reports its setpoint
  this->set_supported_custom_fan_modes({
      "auto", "mute", "low_wind", "mid_low_wind", "mid_wind",
      "mid_high_wind", "high_wind", "strong_wind",
  });
}

void RovsunClimate::set_reported_fan_mode(const std::string &s) {
  this->set_custom_fan_mode_(s.c_str());
}

climate::ClimateTraits RovsunClimate::traits() {
  auto t = climate::ClimateTraits();
  climate::ClimateModeMask modes;
  // The climate OFF mode is the power button; the rest are operating modes.
  modes.insert(climate::CLIMATE_MODE_OFF);
  modes.insert(climate::CLIMATE_MODE_AUTO);
  modes.insert(climate::CLIMATE_MODE_COOL);
  modes.insert(climate::CLIMATE_MODE_DRY);
  modes.insert(climate::CLIMATE_MODE_FAN_ONLY);
  modes.insert(climate::CLIMATE_MODE_HEAT);
  t.set_supported_modes(modes);
  t.set_visual_min_temperature(16);
  t.set_visual_max_temperature(30);
  t.set_visual_target_temperature_step(0.5);
  return t;
}

void RovsunClimate::control(const climate::ClimateCall &call) {
  if (call.get_mode().has_value()) {
    climate::ClimateMode m = *call.get_mode();
    this->mode = m;
    if (m == climate::CLIMATE_MODE_OFF) {
      parent_->control_power(false);
    } else {
      parent_->control_power(true);
      parent_->control_mode(climate_mode_to_code(m));
    }
  }
  if (call.has_custom_fan_mode()) {
    std::string fm = call.get_custom_fan_mode().str();
    this->set_custom_fan_mode_(fm.c_str());
    parent_->control_fan(fan_to_code(fm));
  }
  if (call.get_target_temperature().has_value()) {
    this->target_temperature = *call.get_target_temperature();
    parent_->control_setpoint(*call.get_target_temperature());
  }
  this->publish_state();
}

}  // namespace rovsun_a5
}  // namespace esphome
