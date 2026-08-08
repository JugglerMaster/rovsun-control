#include "rovsun_a5.h"
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

void RovsunA5::setup() { rx_.clear(); }

void RovsunA5::loop() {
  while (this->available()) {
    int c = this->read();
    if (c < 0) break;
    rx_.push_back(static_cast<uint8_t>(c));
    this->process_();
  }
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

void RovsunA5::apply_register_(uint16_t reg, uint32_t value) {
  const char *s;
  switch (reg) {
    case 0x0001:
      if (power_switch_) power_switch_->publish_state(value != 0);
      break;
    case 0x0025:
      if (beep_switch_) beep_switch_->publish_state(value != 0);
      break;
    case 0x0005:
      s = fan_str(static_cast<uint8_t>(value));
      if (fan_select_ && s[0]) fan_select_->publish_state(s);
      break;
    case 0x0011:
      s = vdir_str(static_cast<uint8_t>(value));
      if (vdir_select_ && s[0]) vdir_select_->publish_state(s);
      break;
    case 0x0012:
      s = mode_str(static_cast<uint8_t>(value));
      if (mode_select_ && s[0]) mode_select_->publish_state(s);
      break;
    case 0x0002:
      if (setpoint_number_) setpoint_number_->publish_state(value / 100.0f);
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

  this->write(frame.data(), frame.size());
}

void RovsunA5::control_power(bool on) {
  send_register_(0x0001, {static_cast<uint8_t>(on ? 0x01 : 0x00)});
}
void RovsunA5::control_beep(bool on) {
  send_register_(0x0025, {static_cast<uint8_t>(on ? 0x01 : 0x00)});
}
void RovsunA5::control_fan(uint8_t val) { send_register_(0x0005, {val}); }
void RovsunA5::control_vdir(uint8_t val) { send_register_(0x0011, {val}); }
void RovsunA5::control_mode(uint8_t val) { send_register_(0x0012, {val}); }
void RovsunA5::control_setpoint(float celsius) {
  uint32_t v = static_cast<uint32_t>(celsius * 100.0f);
  send_register_(0x0002, {
                              static_cast<uint8_t>(v >> 24),
                              static_cast<uint8_t>(v >> 16),
                              static_cast<uint8_t>(v >> 8),
                              static_cast<uint8_t>(v),
                          });
}

void RovsunA5::dump_config() {
  ESP_LOGCONFIG(TAG, "Rovsun A5 UART controller");
  LOG_UART_DEVICE(this);
}

}  // namespace rovsun_a5
}  // namespace esphome
