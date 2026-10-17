// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EP_DAISY_BENCH_H_
#define EP_DAISY_BENCH_H_
#include "../shared_control.h"
#include <eurorack_patterns/gestures.h>
#include <eurorack_patterns/timing.h>
#include <cstdint>

namespace bench {
constexpr uint32_t kPeriodUs = 1000;
constexpr uint32_t kGapUs = 10000;
constexpr uint32_t kHoldMs = 600;
constexpr uint32_t kMaxDurationMs = 150000;
constexpr uint32_t kMaxRecords = kMaxDurationMs * 1000 / kPeriodUs;
enum class Role { kTarget };
struct Result {
  bool cadence_valid, debounced, changed;
  uint32_t gesture, actions, state;
  int32_t accepted_ppm, value_ppm, target_ppm;
};
inline int32_t Ppm(float x) { return static_cast<int32_t>(x * 1000000.0f + 0.5f); }

// One foreground owner. A startup-held button has no actionable press. Tap acts
// on qualified release; hold acts once at 600 ms and consumes that release.
class Controls {
 public:
  void Reset(uint32_t target_milli, bool held) {
    control_.Reset(static_cast<float>(target_milli) / 1000.0f);
    button_.Configure(10, 10, held);
    role_ = eurorack_patterns::RoleLatch<Role>();
    target_ = static_cast<float>(target_milli) / 1000.0f;
    previous_us_ = press_ms_ = actions_ = 0;
    started_ = alternate_ = false;
  }
  Result Step(uint32_t us, uint16_t raw, bool adc_valid, bool pressed,
              int32_t external_milli = -1) {
    const bool cadence = !started_ || uint32_t(us - previous_us_) <= kGapUs;
    previous_us_ = us;
    started_ = true;
    if (!cadence) {
      control_.Sample(0.0f, false);
      button_.Observe(pressed, us / 1000, false);
      role_.Cancel(); // An unseen release/repress cannot become a tap or hold.
    }
    uint32_t gesture = 0;
    if (external_milli >= 0) Edit(static_cast<float>(external_milli) / 1000.0f);
    if (button_.Observe(pressed, us / 1000)) {
      if (button_.pressed()) {
        role_.Press(Role::kTarget);
        press_ms_ = us / 1000;
      } else {
        Role role;
        if (role_.Release(role)) {
          alternate_ = !alternate_;
          Edit(alternate_ ? 0.75f : 0.25f);
          gesture = 1;
        }
      }
    }
    if (role_.IsPressed() && !role_.IsConsumed() && button_.pressed() &&
        uint32_t(us / 1000 - press_ms_) >= kHoldMs) {
      role_.Consume();
      Edit(0.5f);
      gesture = 2;
    }
    if (gesture) ++actions_;
    const bool changed = control_.Sample(static_cast<float>(raw) * 100.0f / 65535.0f,
                                        adc_valid);
    return {cadence, button_.pressed(), changed, gesture, actions_,
            static_cast<uint32_t>(control_.state()),
            control_.has_sample() ? Ppm(control_.accepted_percent() / 100.0f) : -1,
            Ppm(control_.value()), Ppm(target_)};
  }
 private:
  void Edit(float target) { control_.ExternalEdit(target); target_ = target; }
  example::SharedControl control_;
  eurorack_patterns::DebouncedButton button_;
  eurorack_patterns::RoleLatch<Role> role_;
  float target_ = 0.0f;
  uint32_t previous_us_ = 0, press_ms_ = 0, actions_ = 0;
  bool started_ = false, alternate_ = false;
};

// Extend raw timer ticks BEFORE converting units. Dividing a wrapping raw
// counter first would give GetUs() a wrap period other than 2^32 microseconds.
class Clock {
 public:
  Clock(uint32_t tick, uint32_t hz) : previous_(tick), hz_(hz) {}
  uint32_t Us(uint32_t tick) {
    ticks_ += uint32_t(tick - previous_);
    previous_ = tick;
    return static_cast<uint32_t>(ticks_ * 1000000ull / hz_);
  }
  uint64_t ticks() const { return ticks_; }
 private:
  uint64_t ticks_ = 0;
  uint32_t previous_, hz_;
};

struct Record {
  uint32_t seq, time_us, adc_us, work_us, raw, adc_valid, injected, pressed;
  int32_t external_milli;
  Result result;
  uint32_t missed;
};
// Fixed-rate deadlines, with explicit skipped slots and no catch-up samples.
class Schedule {
 public:
  bool Due(uint32_t us) const { return us >= next_; }
  uint32_t Take(uint32_t us) {
    const uint32_t skipped = (us - next_) / kPeriodUs;
    next_ += (skipped + 1) * kPeriodUs;
    return skipped;
  }
 private:
  uint32_t next_ = 0;
};
} // namespace bench
#endif
