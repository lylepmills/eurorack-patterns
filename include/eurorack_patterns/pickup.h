// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EURORACK_PATTERNS_PICKUP_H_
#define EURORACK_PATTERNS_PICKUP_H_

#include <algorithm>
#include <cmath>

namespace eurorack_patterns {

// A small pickup decision in caller-mapped, consistent units. The caller owns
// physical-to-parameter mapping, motion filtering, and applying the sample.
class PickupLatch {
 public:
  enum class State { kUnarmed, kWaiting, kTracking, kUnreachable };

  // Endpoints may be reversed or equal. A valid configuration replaces the
  // previous one and leaves the latch unarmed. Invalid input changes nothing.
  bool Configure(float endpoint_a, float endpoint_b, float tolerance) {
    if (!std::isfinite(endpoint_a) || !std::isfinite(endpoint_b) ||
        !std::isfinite(tolerance) || tolerance <= 0.0f)
      return false;
    lower_ = std::min(endpoint_a, endpoint_b);
    upper_ = std::max(endpoint_a, endpoint_b);
    tolerance_ = tolerance;
    configured_ = true;
    Disarm();
    return true;
  }

  // A target outside the inclusive endpoint interval cannot be picked up.
  // Accepted arms clear sample history, including when the target is unreachable.
  // Invalid targets or a missing configuration leave all state unchanged.
  bool Arm(float target) {
    if (!configured_ || !std::isfinite(target)) return false;
    target_ = target;
    have_previous_ = false;
    state_ = (target < lower_ || target > upper_) ? State::kUnreachable
                                                  : State::kWaiting;
    return true;
  }

  // Returns permission to apply this sample, not a changed-value event.
  // Invalid, nonfinite, or out-of-range samples never apply and break crossing
  // history, while preserving the armed state and target. Waiting catches on a
  // strict near match or a crossing between consecutive valid samples.
  bool Observe(float mapped_sample, bool valid = true) {
    if (!valid || !std::isfinite(mapped_sample) || !configured_ ||
        mapped_sample < lower_ || mapped_sample > upper_) {
      have_previous_ = false;
      return false;
    }
    if (state_ == State::kTracking) return true;
    if (state_ != State::kWaiting) return false;

    const bool near = std::fabs(mapped_sample - target_) < tolerance_;
    const bool crossed = have_previous_ &&
        ((previous_ < target_ && mapped_sample > target_) ||
         (previous_ > target_ && mapped_sample < target_));
    previous_ = mapped_sample;
    have_previous_ = true;
    if (!near && !crossed) return false;
    state_ = State::kTracking;
    return true;
  }

  // Retain the range configuration for a future Arm().
  void Disarm() {
    state_ = State::kUnarmed;
    have_previous_ = false;
    target_ = 0.0f;
  }

  State state() const { return state_; }
  bool configured() const { return configured_; }

 private:
  float lower_ = 0.0f;
  float upper_ = 0.0f;
  float tolerance_ = 0.0f;
  float target_ = 0.0f;
  float previous_ = 0.0f;
  bool configured_ = false;
  bool have_previous_ = false;
  State state_ = State::kUnarmed;
};

}  // namespace eurorack_patterns
#endif  // EURORACK_PATTERNS_PICKUP_H_
