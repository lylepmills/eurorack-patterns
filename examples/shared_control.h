// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EP_EXAMPLE_SHARED_CONTROL_H_
#define EP_EXAMPLE_SHARED_CONTROL_H_
#include <eurorack_patterns/controls.h>
#include <eurorack_patterns/pickup.h>

namespace example {
// Example application policy, not a library API. One owner calls every method.
// The physical input is percent; the destination uses continuous units [0,1].
class SharedControl {
 public:
  bool Reset(float initial) {
    if (!ValidValue(initial)) return false;
    pickup_.Configure(0.0f, 1.0f, 0.005f);
    have_sample_ = false;
    value_ = initial;
    return pickup_.Arm(initial);
  }
  // Call for every preset/bank/external edit, even if the number is unchanged.
  bool ExternalEdit(float target) {
    if (!ValidValue(target) || !pickup_.Arm(target)) return false;
    value_ = target;
    // Retain the motion anchor, but seed the new ownership epoch explicitly.
    if (have_sample_) pickup_.Observe(accepted_ / 100.0f);
    return true;
  }
  // Return a changed-value event. The latch itself returns apply permission.
  bool Sample(float percent, bool valid) {
    if (!valid || !eurorack_patterns::ValidPercent(percent)) {
      pickup_.Observe(0.0f, false);  // BEFORE any motion rejection.
      have_sample_ = false;
      return false;
    }
    if (!have_sample_) {
      accepted_ = percent;
      have_sample_ = true;
    } else if (!eurorack_patterns::AcceptMotion(percent, accepted_)) {
      return false;
    }
    const float mapped = accepted_ / 100.0f;
    if (!pickup_.Observe(mapped)) return false;
    const bool changed = mapped != value_;
    value_ = mapped;
    return changed;
  }
  bool has_sample() const { return have_sample_; }
  float accepted_percent() const { return accepted_; }
  float value() const { return value_; }
  eurorack_patterns::PickupLatch::State state() const { return pickup_.state(); }
 private:
  static bool ValidValue(float value) {
    return std::isfinite(value) && value >= 0.0f && value <= 1.0f;
  }
  eurorack_patterns::PickupLatch pickup_;
  float value_ = 0.0f;
  float accepted_ = 0.0f;
  bool have_sample_ = false;
};
}  // namespace example
#endif
