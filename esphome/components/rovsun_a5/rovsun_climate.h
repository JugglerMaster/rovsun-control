#pragma once

#include <string>
#include "esphome/components/climate/climate.h"
#include "rovsun_a5.h"

namespace esphome {
namespace rovsun_a5 {

class RovsunClimate : public climate::Climate {
 public:
  RovsunClimate();

  void set_parent(RovsunA5 *parent) { parent_ = parent; }

  void control(const climate::ClimateCall &call) override;
  climate::ClimateTraits traits() override;

  // Push a device-reported fan level (custom mode string) to the UI without
  // re-triggering a control command back to the unit.
  void set_reported_fan_mode(const std::string &s);

 protected:
  RovsunA5 *parent_{nullptr};
};

}  // namespace rovsun_a5
}  // namespace esphome
