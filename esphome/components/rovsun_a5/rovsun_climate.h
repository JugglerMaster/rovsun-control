#pragma once

#include "esphome/components/climate/climate.h"
#include "rovsun_a5.h"

namespace esphome {
namespace rovsun_a5 {

class RovsunClimate : public climate::Climate {
 public:
  void set_parent(RovsunA5 *parent) { parent_ = parent; }

  void setup() override;
  void control(const climate::ClimateCall &call) override;
  climate::ClimateTraits traits() override;

 protected:
  RovsunA5 *parent_{nullptr};
};

}  // namespace rovsun_a5
}  // namespace esphome
