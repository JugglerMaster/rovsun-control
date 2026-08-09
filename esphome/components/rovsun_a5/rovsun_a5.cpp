#include "rovsun_a5.h"
#include "rovsun_climate.h"
#include "esphome/core/log.h"

namespace esphome {
namespace rovsun_a5 {

static const char *TAG = "rovsun_a5";

static const char *fan_str(uint8_t v) {
  switch (v) {
    case 0: return "auto";
    case 1: return "mute";
    case 2: return "low_wind";
    case 3: return "mid_low_wind";
    case 4: return "mid_wind";
    case 5: return "mid_high_wind";
    case 6: return "high_wind";
    case 7: return "strong_wind";
    default: return "";
  }
}

static const char *vdir_str(uint8_t v) {
  switch (v) {
    case 1: return "flow";
    case 2: return "up";
    case 3: return "down";
    case 9: return "up_fix";
    case 0x0A: return "above_fix";
    case 0x0B: return "middle_fix";
    case 0x0C: return "above_down_fix";
    case 0x0D: return "down_fix";
    default: return "";
  }
}

static const char *mode_str(uint8_t v) {
  switch (v) {
    case 0: return "auto";
    case 1: return "cool";
    case 2: return "dry";
    case 3: return "fan_only";
    case 4: return "heat";
    default: return "";
  }
}

static const char *sleep_str(uint8_t v) {
  switch (v) {
    case 1: return "standard";
    case 2: return "aged";
    case 3: return "child";
    default: return "off";
  }
}

static const char *gen_str(uint8_t v) {
  switch (v) {
    case 2: return "lv2";
    case 3: return "lv3";
    default: return "lv1";
  }
}

static const char *lrdir_str(uint8_t v) {
  switch (v) {
    case 2: return "left_flow";
    case 3: return "middle_flow";
    case 4: return "right_flow";
    case 9: return "left_fix";
    case 0x0A: return "a_bit_left_fix";
    case 0x0B: return "middle_fix";
    case 0x0C: return "a_bit_right_fix";
    case 0x0D: return "left_right_flow";
    default: return "";
  }
}

void RovsunA5::setup() { rx_.clear(); }

void RovsunA5::loop() {
  while (this->available()) {
    int c = this->read();
    if (c < 0) break;
    rx_.push_back(static_cast<uint8_t>(c));
    this->process_();
  }
}

void RovsunA5::log_frame_(const char *dir, const uint8_t *data, size_t len) {
  if (!log_raw_) return;
  std::string s;
  char buf[4];
  for (size_t i = 0; i < len; i++) {
    snprintf(buf, sizeof(buf), "%02X ", data[i]);
    s += buf;
  }
  ESP_LOGD(TAG, "%s: %s", dir, s.c_str());
}

void RovsunA5::process_() {
  size_t i = 0;
  while (i + 8 <= rx_.size()) {
    if (rx_[i] != 0xA5 || rx_[i + 1] != 0x01 ||
        (rx_[i + 2] != 0x01 && rx_[i + 2] != 0x00)) {
      i++;
      continue;
    }
    uint8_t len = rx_[i + 7];
    if (len < 10 || i + len > rx_.size()) {
      i++;
      continue;
    }
    this->log_frame_("RX", &rx_[i], len);
    this->parse_frame_(&rx_[i], len);
    rx_.erase(rx_.begin() + i, rx_.begin() + i + len);
    i = 0;  // frame removed from the front; rescan
  }
  // Bound the buffer so a stream of garbage cannot exhaust memory.
  if (rx_.size() > 1024) {
    rx_.erase(rx_.begin(), rx_.begin() + (rx_.size() - 512));
  }
}

uint16_t RovsunA5::crc16_xmodem_(const uint8_t *data, size_t len) {
  uint16_t crc = 0;
  for (size_t i = 0; i < len; i++) {
    crc ^= static_cast<uint16_t>(data[i]) << 8;
    for (uint8_t bit = 0; bit < 8; bit++) {
      if (crc & 0x8000) {
        crc = static_cast<uint16_t>((crc << 1) ^ 0x1021);
      } else {
        crc = static_cast<uint16_t>(crc << 1);
      }
    }
  }
  return crc;
}

void RovsunA5::parse_frame_(const uint8_t *f, size_t len) {
  // CRC covers the 8-byte header plus the body excluding the two CRC bytes.
  std::vector<uint8_t> crcbuf(f, f + 8);
  crcbuf.insert(crcbuf.end(), f + 10, f + len);
  uint16_t calc = crc16_xmodem_(crcbuf.data(), crcbuf.size());
  uint16_t got = (static_cast<uint16_t>(f[8]) << 8) | f[9];
  if (calc != got) {
    ESP_LOGW(TAG, "CRC mismatch: got %04X calc %04X", got, calc);
    return;
  }

  // Only parse state reports (cmd 0x21 with the 0C 0C body prefix).
  if (f[3] != 0x21) return;
  const uint8_t *body = f + 10;
  size_t body_len = len - 10;
  if (body_len < 2 || body[0] != 0x0C || body[1] != 0x0C) return;

  size_t idx = 2;
  // Registers observed with 4-byte values (big-endian). All others are 1 byte.
  while (idx + 2 <= body_len) {
    uint16_t reg = (static_cast<uint16_t>(body[idx]) << 8) | body[idx + 1];
    bool wide = (reg == 0x0002 || reg == 0x0003 || reg == 0x000D ||
                 reg == 0x0227);
    size_t w = wide ? 4 : 1;
    if (idx + 2 + w > body_len) break;
    uint32_t value = 0;
    for (size_t k = 0; k < w; k++) {
      value = (value << 8) | body[idx + 2 + k];
    }
    this->apply_register_(reg, value);
    idx += 2 + w;
  }
}

void RovsunA5::update_climate_() {
  if (climate_ == nullptr) return;
  // Power is a separate switch entity, so the climate mode always reflects the
  // AC's current mode (never OFF).
  climate_->mode = mode_code_to_climate_(mode_);
  const char *fs = fan_str(fan_);
  if (fs[0]) climate_->set_reported_fan_mode(fs);
  climate_->target_temperature = setpoint_ / 100.0f;
  climate_->publish_state();
}

climate::ClimateMode RovsunA5::mode_code_to_climate_(uint8_t v) {
  switch (v) {
    case 1: return climate::CLIMATE_MODE_COOL;
    case 2: return climate::CLIMATE_MODE_DRY;
    case 3: return climate::CLIMATE_MODE_FAN_ONLY;
    case 4: return climate::CLIMATE_MODE_HEAT;
    default: return climate::CLIMATE_MODE_AUTO;
  }
}

void RovsunA5::restore_settings_() {
  if (cmd_fan_ != 0xFF) control_fan(cmd_fan_);
  if (cmd_vdir_ != 0xFF) control_vdir(cmd_vdir_);
  if (cmd_mode_ != 0xFF) control_mode(cmd_mode_);
  if (cmd_setpoint_ != 0) control_setpoint(cmd_setpoint_ / 100.0f);
  if (cmd_beep_ != 0xFF) control_beep(cmd_beep_);
  if (cmd_light_ != 0xFF) control_light(cmd_light_);
  if (cmd_drying_ != 0xFF) control_drying(cmd_drying_);
  if (cmd_sleep_ != 0xFF) control_sleep(cmd_sleep_);
  if (cmd_lrdir_ != 0xFF) control_lrdir(cmd_lrdir_);
  // NOTE: generator mode is intentionally excluded from the power-on replay.
  // It has no "off" and defaults to lv1; re-asserting it on every AC power-on
  // is unwanted. It remains fully controllable from HA and reflects IR-remote
  // changes via the 0x21 report.
}

void RovsunA5::apply_register_(uint16_t reg, uint32_t value) {
  const char *s;
  switch (reg) {
    case 0x0001: {
      bool was_on = power_on_;
      power_on_ = value != 0;
      if (power_switch_) power_switch_->publish_state(power_on_);
      if (restore_on_power_on_ && power_on_ && (!seen_any_ || !was_on)) {
        // Replay desired settings on first contact (covers a breaker cycle
        // that also restarted ESPHome) and on every genuine off->on transition
        // (power restored, or IR/HA turned the unit on).
        restore_settings_();
      }
      seen_any_ = true;
      update_climate_();
      break;
    }
    case 0x0025:
      if (beep_switch_) beep_switch_->publish_state(value != 0);
      break;
    case 0x0005:
      fan_ = static_cast<uint8_t>(value);
      update_climate_();
      break;
    case 0x0011:
      vdir_ = static_cast<uint8_t>(value);
      s = vdir_str(vdir_);
      if (vdir_select_ && s[0]) vdir_select_->publish_state(s);
      update_climate_();
      break;
    case 0x0012:
      mode_ = static_cast<uint8_t>(value);
      update_climate_();
      break;
    case 0x0002:
      setpoint_ = value;
      update_climate_();
      break;
    case 0x001E:
      if (light_switch_) light_switch_->publish_state(value != 0);
      break;
    case 0x0027:
      if (drying_switch_) drying_switch_->publish_state(value != 0);
      break;
    case 0x0022:
      s = sleep_str(static_cast<uint8_t>(value));
      if (sleep_select_ && s[0]) sleep_select_->publish_state(s);
      break;
    case 0x002D:
      gen_state_ = static_cast<uint8_t>(value);
      s = gen_str(static_cast<uint8_t>(value));
      if (generator_select_ && s[0]) generator_select_->publish_state(s);
      break;
    case 0x000E:
      s = lrdir_str(static_cast<uint8_t>(value));
      if (lrdir_select_ && s[0]) lrdir_select_->publish_state(s);
      break;
    default:
      break;
  }
}

void RovsunA5::send_register_(uint16_t reg, const std::vector<uint8_t> &value) {
  size_t total = 8 + 2 + 2 + 2 + value.size();  // hdr + crc + 0A0A + reg + value
  std::vector<uint8_t> frame(total);
  frame[0] = 0xA5;
  frame[1] = 0x01;
  frame[2] = 0x01;
  frame[3] = 0x21;
  frame[4] = seq_++;
  frame[5] = 0x00;
  frame[6] = 0x00;
  frame[7] = static_cast<uint8_t>(total);
  frame[8] = 0x00;  // CRC placeholder
  frame[9] = 0x00;
  frame[10] = 0x0A;
  frame[11] = 0x0A;
  frame[12] = static_cast<uint8_t>(reg >> 8);
  frame[13] = static_cast<uint8_t>(reg & 0xFF);
  for (size_t i = 0; i < value.size(); i++) frame[14 + i] = value[i];

  std::vector<uint8_t> crcbuf(frame.begin(), frame.begin() + 8);
  crcbuf.insert(crcbuf.end(), frame.begin() + 10, frame.end());
  uint16_t crc = crc16_xmodem_(crcbuf.data(), crcbuf.size());
  frame[8] = static_cast<uint8_t>(crc >> 8);
  frame[9] = static_cast<uint8_t>(crc & 0xFF);

  this->log_frame_("TX", frame.data(), frame.size());
  for (size_t i = 0; i < frame.size(); i++) this->write(frame[i]);
  this->flush();
}

void RovsunA5::control_power(bool on) {
  // Don't spam redundant power commands (each one makes the AC beep).
  if (on == power_on_) return;
  send_register_(0x0001, {static_cast<uint8_t>(on ? 0x01 : 0x00)});
}
void RovsunA5::control_beep(bool on) {
  cmd_beep_ = on ? 0x01 : 0x00;
  send_register_(0x0025, {static_cast<uint8_t>(cmd_beep_)});
}
void RovsunA5::control_fan(uint8_t val) {
  cmd_fan_ = val;
  send_register_(0x0005, {val});
}
void RovsunA5::control_vdir(uint8_t val) {
  cmd_vdir_ = val;
  send_register_(0x0011, {val});
}
void RovsunA5::control_mode(uint8_t val) {
  cmd_mode_ = val;
  send_register_(0x0012, {val});
}
void RovsunA5::control_setpoint(float celsius) {
  uint32_t v = static_cast<uint32_t>(celsius * 100.0f);
  cmd_setpoint_ = v;
  send_register_(0x0002, {
                              static_cast<uint8_t>(v >> 24),
                              static_cast<uint8_t>(v >> 16),
                              static_cast<uint8_t>(v >> 8),
                              static_cast<uint8_t>(v),
                          });
}
void RovsunA5::control_light(bool on) {
  cmd_light_ = on ? 0x01 : 0x00;
  send_register_(0x001E, {static_cast<uint8_t>(cmd_light_)});
}
void RovsunA5::control_drying(bool on) {
  cmd_drying_ = on ? 0x01 : 0x00;
  send_register_(0x0027, {static_cast<uint8_t>(cmd_drying_)});
}
void RovsunA5::control_sleep(uint8_t val) {
  cmd_sleep_ = val;
  send_register_(0x0022, {val});
}
void RovsunA5::control_generator(uint8_t val) {
  // Don't re-send the value the AC already reports (e.g. an HA echo of the
  // current state, or an IR-remote change we already observed).
  if (val == gen_state_) return;
  gen_state_ = val;
  cmd_gen_ = val;
  send_register_(0x002D, {val});
}
void RovsunA5::control_lrdir(uint8_t val) {
  cmd_lrdir_ = val;
  send_register_(0x000E, {val});
}

void RovsunA5::dump_config() {
  ESP_LOGCONFIG(TAG, "Rovsun A5 UART controller");
}

}  // namespace rovsun_a5
}  // namespace esphome
