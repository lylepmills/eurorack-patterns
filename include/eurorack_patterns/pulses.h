// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EURORACK_PATTERNS_PULSES_H_
#define EURORACK_PATTERNS_PULSES_H_

#include <cstdint>

namespace eurorack_patterns {

enum class PulseRetriggerPolicy {
  // A trigger during an active pulse starts its width again from now.
  kRestart,
  // A trigger during an active pulse leaves its original expiry unchanged.
  kIgnoreWhileActive
};

// Logical one-shot pulse state. A single caller owns configuration, triggers,
// cancellation, and output service; no synchronization or hardware timer is
// provided. Timestamps are caller-defined uint32 ticks. Supply monotonic time
// modulo 2^32 with less than 2^31 ticks between calls. Configure accepts widths
// below 2^31 ticks; zero disables new pulses.
class PulseTimer {
 public:
  PulseTimer() : duration_(0), started_(0),
      policy_(PulseRetriggerPolicy::kRestart), configured_(false), active_(false) {}

  // A successful configuration cancels any active pulse and requires the host
  // to drive its output inactive. Invalid input leaves all state unchanged.
  bool Configure(uint32_t duration, PulseRetriggerPolicy policy) {
    if (duration >= 0x80000000u ||
        (policy != PulseRetriggerPolicy::kRestart &&
         policy != PulseRetriggerPolicy::kIgnoreWhileActive)) return false;
    duration_ = duration;
    policy_ = policy;
    configured_ = true;
    active_ = false;
    return true;
  }

  // First expires an overdue pulse. Returns true if this trigger was accepted;
  // false if unconfigured, disabled, or ignored while active. Acceptance during
  // an already-active restart is NOT a new physical output edge.
  bool Trigger(uint32_t now) {
    if (!configured_) return false;
    Advance(now);
    if (duration_ == 0 ||
        (active_ && policy_ == PulseRetriggerPolicy::kIgnoreWhileActive))
      return false;
    started_ = now;
    active_ = true;
    return true;
  }

  // Returns true exactly when this call expires an active pulse. The host must
  // service and write the inactive output; late service extends physical width.
  bool Advance(uint32_t now) {
    if (!active_ || uint32_t(now - started_) < duration_) return false;
    active_ = false;
    return true;
  }

  // Immediately makes logical state inactive and invalidates its old deadline.
  // Returns true if a pulse was active. The host must drive inactive now.
  bool Cancel() {
    const bool was_active = active_;
    active_ = false;
    return was_active;
  }

  bool configured() const { return configured_; }
  bool active() const { return active_; }
  uint32_t duration() const { return duration_; }
  PulseRetriggerPolicy policy() const { return policy_; }

 private:
  uint32_t duration_;
  uint32_t started_;
  PulseRetriggerPolicy policy_;
  bool configured_;
  bool active_;
};

}  // namespace eurorack_patterns

#endif  // EURORACK_PATTERNS_PULSES_H_
