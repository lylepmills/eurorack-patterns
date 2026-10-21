// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EP_DAISY_PULSE_GENERATOR_H_
#define EP_DAISY_PULSE_GENERATOR_H_
#include <cstddef>
#include <cstdint>

// Test apparatus, not a production control component. A second MCU owns this
// timetable. The receiving MCU's faults cannot postpone these deadlines.
namespace pulsegen {
constexpr uint32_t kMaxEdges = 64, kMaxUs = 30000000;
constexpr uint32_t kMinIntervalUs = 100, kFirstUs = 100000, kMaxLateUs = 25;
struct Plan {
  uint32_t token = 0, count = 0, times[kMaxEdges]{};
  bool Valid() const {
    if (count < 2 || count > kMaxEdges || count % 2 || times[0] < kFirstUs)
      return false;
    for (uint32_t i = 0; i < count; ++i)
      if (times[i] > kMaxUs || (i && (times[i] <= times[i-1] ||
                                    times[i] - times[i-1] < kMinIntervalUs))) return false;
    return true;
  }
};
// Strict unsigned decimal parsing: no signs, whitespace, overflow or suffixes.
inline bool Number(const char*& p, uint32_t& value) {
  value = 0;
  if (*p < '0' || *p > '9') return false;
  do {
    const uint32_t digit = static_cast<uint32_t>(*p++ - '0');
    if (value > (UINT32_MAX - digit) / 10) return false;
    value = value * 10 + digit;
  } while (*p >= '0' && *p <= '9');
  return true;
}
inline bool ParsePlan(const char* p, Plan& out) {
  Plan candidate;
  if (*p++ != 'P' || *p++ != ',' || !Number(p, candidate.token) || *p++ != ',' ||
      !Number(p, candidate.count) || candidate.count > kMaxEdges) return false;
  for (uint32_t i = 0; i < candidate.count; ++i)
    if (*p++ != ',' || !Number(p, candidate.times[i])) return false;
  if (*p || !candidate.Valid()) return false;
  out = candidate;
  return true;
}
inline bool ParseRun(const char* p, uint32_t& token) {
  return *p++ == 'R' && *p++ == ',' && Number(p, token) && *p == '\0';
}
// The adapter must write !pressed immediately while interrupts are masked,
// then record the post-write time too. A late poll aborts; it never compresses
// multiple overdue edges into a misleading catch-up burst.
class Sequence {
 public:
  enum Result { kWaiting, kEdge, kDone, kLate };
  explicit Sequence(const Plan& plan) : plan_(plan) {}
  Result Poll(uint32_t us, bool& pressed) {
    if (failed_) { pressed = false; return kLate; }
    if (next_ == plan_.count) { pressed = false; return kDone; }
    if (us < plan_.times[next_]) return kWaiting;
    if (us - plan_.times[next_] > kMaxLateUs) {
      failed_ = true; pressed = false; return kLate;
    }
    pressed = (next_++ % 2) == 0;
    return kEdge;
  }
  uint32_t count() const { return next_; }
 private:
  const Plan& plan_;
  uint32_t next_ = 0;
  bool failed_ = false;
};
} // namespace pulsegen
#endif
