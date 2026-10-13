// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EURORACK_PATTERNS_TIMING_H_
#define EURORACK_PATTERNS_TIMING_H_
#include <cstdint>

namespace eurorack_patterns {

// Mechanical contacts only. Clock/trigger acquisitions need edge capture,
// not this stable-duration filter. Time is caller-supplied unsigned milliseconds.
// Call from one owner with forward timestamps (wrap is allowed); gaps between
// observations must be < 2^31 ms. Durations must be < 2^31 ms as well.
class DebouncedButton {
 public:
  DebouncedButton() : on_ms_(0), off_ms_(0), started_(0), configured_(false),
      state_(false), candidate_(false), pending_(false) {}
  // The caller supplies a known initial logical state; this does not emit an event.
  // Invalid configuration leaves the instance unchanged. Zero duration is immediate.
  bool Configure(uint32_t on_ms, uint32_t off_ms, bool initial = false) {
    if (on_ms >= 0x80000000u || off_ms >= 0x80000000u) return false;
    on_ms_ = on_ms; off_ms_ = off_ms; state_ = candidate_ = initial;
    pending_ = false; configured_ = true; return true;
  }
  // Returns true once for a stable state transition. Invalid observations break
  // the candidate's continuity without changing the published state.
  bool Observe(bool pressed, uint32_t now_ms, bool valid = true) {
    if (!configured_) return false;
    if (!valid || pressed == state_) { pending_ = false; return false; }
    if (!pending_ || candidate_ != pressed) {
      candidate_ = pressed; started_ = now_ms; pending_ = true;
    }
    const uint32_t duration = pressed ? on_ms_ : off_ms_;
    if (uint32_t(now_ms - started_) < duration) return false;
    state_ = pressed; pending_ = false; return true;
  }
  bool pressed() const { return state_; }
  bool pending() const { return pending_; }
 private:
  uint32_t on_ms_, off_ms_, started_;
  bool configured_, state_, candidate_, pending_;
};

}  // namespace eurorack_patterns
#endif
