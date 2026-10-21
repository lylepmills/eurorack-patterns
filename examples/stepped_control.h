// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EP_EXAMPLE_STEPPED_CONTROL_H_
#define EP_EXAMPLE_STEPPED_CONTROL_H_

#include <eurorack_patterns/pickup.h>
#include <cmath>

namespace example {
// Example policy, not an installed API. One owner serializes samples, external
// edits and destination access. The synchronous destination supplies
// ReadNormalized() and WriteNormalized(float); writes may snap or reject.
// Expected values: {0, .25, .5, .75, 1}; nearest step, midpoint ties upward.
template <typename Destination>
class SteppedControl {
 public:
  using State = eurorack_patterns::PickupLatch::State;
  enum class WriteResult { kNone, kMatched, kMismatch };

  explicit SteppedControl(Destination& destination) : destination_(destination) {
    // Integer step indices: strict tolerance .5 matches only the same step.
    pickup_.Configure(0.0f, 4.0f, 0.5f);
    Rearm();
  }

  // Call after EVERY external edit, preset or bank change, even an equal value.
  // Discard old history; unsupported readback blocks writes until explicit
  // recovery changes the destination to a supported value and calls Rearm().
  bool Rearm() { return ArmValue(destination_.ReadNormalized()); }

  WriteResult Sample(float normalized, bool valid) {
    if (!valid || !std::isfinite(normalized) || normalized < 0.0f ||
        normalized > 1.0f) {
      pickup_.Observe(0.0f, false);
      return WriteResult::kNone;
    }
    const int step = SnappedStep(normalized);
    if (!reachable_ || !pickup_.Observe(static_cast<float>(step)))
      return WriteResult::kNone;

    destination_.WriteNormalized(normalized);
    value_ = destination_.ReadNormalized();  // Never report the request as fact.
    if (value_ != static_cast<float>(step) * 0.25f) {
      ArmValue(value_);  // Rejected/adjusted writes end this ownership epoch.
      return WriteResult::kMismatch;
    }
    return WriteResult::kMatched;
  }

  float value() const { return value_; }  // Most recent actual readback, for UI.
  State state() const { return reachable_ ? pickup_.state() : State::kUnreachable; }

 private:
  static int SnappedStep(float normalized) {
    for (int step = 0; step < 4; ++step)
      if (normalized < (static_cast<float>(step) + 0.5f) * 0.25f) return step;
    return 4;
  }

  bool ArmValue(float stored) {
    pickup_.Disarm();
    value_ = stored;
    reachable_ = false;
    // Exact membership, not just interval bounds. These quarters are exactly
    // representable; an arbitrary scale should use its own canonical step IDs.
    for (int step = 0; step <= 4; ++step) {
      if (stored != static_cast<float>(step) * 0.25f) continue;
      reachable_ = true;
      return pickup_.Arm(static_cast<float>(step));
    }
    return false;
  }

  Destination& destination_;
  eurorack_patterns::PickupLatch pickup_;
  float value_ = 0.0f;
  bool reachable_ = false;
};
}  // namespace example
#endif
