// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EP_DAISY_EXPERIMENT_H_
#define EP_DAISY_EXPERIMENT_H_
#include <cstdint>

namespace bench {
enum Scenario : uint32_t {
  kManual, kTargets, kGap, kStall, kLoad,
  kPressStall, kHoldStall, kReleaseStall, kPressAdcGap,
  kPickupGapUp, kPickupGapDown, kMovingTarget, kStartup
};
constexpr uint32_t kStartupDurationMs = 20000;
struct Stimulus {
  int32_t trigger = -1, begin = -1, end = -1;
};

// Bench stimulus scheduling, separate from the controls under test. Triggers
// use observed raw input edges, not the gesture/pickup result being measured.
// All times fit the bounded 150-second experiment, with -1 meaning not observed.
class Experiment {
 public:
  Experiment(uint32_t scenario, bool held) : scenario_(scenario), pressed_(held) {}
  uint32_t Stall(uint32_t us) {
    if (stall_done_) return 0;
    if (scenario_ == kStall && us >= 5000000) {
      stall_done_ = true;
      return 25;
    }
    if (scenario_ >= kPressStall && scenario_ <= kReleaseStall &&
        stimulus_.trigger >= 0 && us >= due_) {
      stimulus_.begin = static_cast<int32_t>(us);
      stall_done_ = true;
      return 25;
    }
    return 0;
  }
  void EndStall(uint32_t us) {
    if (scenario_ >= kPressStall && scenario_ <= kReleaseStall)
      stimulus_.end = static_cast<int32_t>(us);
  }
  bool InvalidAdc(uint32_t us) {
    if (scenario_ == kGap) return us >= 5000000 && us < 5250000;
    if (scenario_ < kPressAdcGap || scenario_ > kPickupGapDown || stimulus_.trigger < 0)
      return false;
    if (us < due_) return false;
    if (stimulus_.begin < 0) {
      stimulus_.begin = static_cast<int32_t>(us);
      gap_end_ = us + (scenario_ == kPressAdcGap ? 250000 : 1000000);
    }
    if (us < gap_end_) return true;
    if (stimulus_.end < 0) stimulus_.end = static_cast<int32_t>(us);
    return false;
  }
  int32_t Observe(uint32_t us, uint16_t raw, bool valid, bool pressed) {
    const bool press = pressed && !pressed_;
    const bool release = !pressed && pressed_ && saw_press_;
    saw_press_ = saw_press_ || press;
    pressed_ = pressed;
    bool trigger = false;
    if (stimulus_.trigger < 0) {
      if (scenario_ == kPressStall || scenario_ == kHoldStall || scenario_ == kPressAdcGap)
        trigger = press;
      if (scenario_ == kReleaseStall) trigger = release;
      if (valid && have_raw_) {
        if (scenario_ == kPickupGapUp) trigger = previous_raw_ < 9831 && raw >= 9831;
        if (scenario_ == kPickupGapDown) trigger = previous_raw_ > 22937 && raw <= 22937;
        if (scenario_ == kMovingTarget) trigger = previous_raw_ < 32768 && raw >= 32768;
      }
    }
    have_raw_ = valid;
    previous_raw_ = raw;
    if (!trigger) return -1;
    stimulus_.trigger = static_cast<int32_t>(us);
    const uint32_t delay = scenario_ == kPressStall ? 100000 :
                           scenario_ == kHoldStall ? 605000 :
                           scenario_ == kPressAdcGap ? 20000 : 1;
    due_ = us + delay;
    if (scenario_ == kMovingTarget) {
      stimulus_.begin = stimulus_.end = static_cast<int32_t>(us);
      return 750;
    }
    return -1;
  }
  const Stimulus& stimulus() const { return stimulus_; }
 private:
  uint32_t scenario_, due_ = 0, gap_end_ = 0;
  bool pressed_, saw_press_ = false, have_raw_ = false, stall_done_ = false;
  uint16_t previous_raw_ = 0;
  Stimulus stimulus_;
};
} // namespace bench
#endif
