// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EURORACK_PATTERNS_EVENTS_H_
#define EURORACK_PATTERNS_EVENTS_H_

#include <cmath>
#include <cstdint>
#include <type_traits>

namespace eurorack_patterns {

enum class HighAcquisitionPolicy {
  // An initial/reacquired high level establishes state without an edge.
  kSeedSilently,
  // An initial/reacquired high level contributes one event.
  kCountAsRise
};

// Schmitt rising-edge capture for one sampled input. The producer calls
// Observe at its acquisition rate; a slower consumer drains event counts.
// Single owner only: callers crossing interrupt/thread domains must provide
// synchronization around Observe, Consume, and state inspection.
template <typename Sample>
class RisingEdgeCapture {
 public:
  static_assert(std::is_arithmetic<Sample>::value,
                "RisingEdgeCapture requires an arithmetic sample type");
  RisingEdgeCapture()
      : low_(), high_(), capacity_(0), policy_(HighAcquisitionPolicy::kSeedSilently),
        configured_(false), level_known_(false), high_level_(false),
        pending_(0), overflowed_(false) {}

  // low < high and capacity > 0 are required. Invalid configuration leaves
  // the previous configuration and state unchanged. Units are caller-defined.
  bool Configure(Sample low, Sample high, uint16_t capacity,
                 HighAcquisitionPolicy policy) {
    if (!std::isfinite(low) || !std::isfinite(high) ||
        !(low < high) || capacity == 0 ||
        (policy != HighAcquisitionPolicy::kSeedSilently &&
         policy != HighAcquisitionPolicy::kCountAsRise)) return false;
    low_ = low;
    high_ = high;
    capacity_ = capacity;
    policy_ = policy;
    configured_ = true;
    Reset();
    return true;
  }

  // Returns true when an event was enqueued. An invalid acquisition loses
  // Schmitt level knowledge but preserves pending events and overflow. A
  // sample strictly between thresholds cannot establish an unknown level.
  bool Observe(Sample value, bool valid = true) {
    if (!configured_) return false;
    if (!valid || !std::isfinite(value)) {
      level_known_ = false;
      return false;
    }
    if (!level_known_) {
      if (value <= low_) {
        level_known_ = true;
        high_level_ = false;
        return false;
      }
      if (value >= high_) {
        level_known_ = true;
        high_level_ = true;
        return policy_ == HighAcquisitionPolicy::kCountAsRise && Enqueue();
      }
      return false;
    }
    if (high_level_) {
      if (value <= low_) high_level_ = false;
      return false;
    }
    if (value >= high_) {
      high_level_ = true;
      return Enqueue();
    }
    return false;
  }

  // Removes at most maximum events; maximum == 0 is a harmless no-op.
  uint16_t Consume(uint16_t maximum) {
    const uint16_t taken = pending_ < maximum ? pending_ : maximum;
    pending_ = static_cast<uint16_t>(pending_ - taken);
    return taken;
  }

  // Overflow stays latched until explicitly cleared; draining does not clear
  // it. Reset clears queue, overflow, and level knowledge, retaining config.
  void ClearOverflow() { overflowed_ = false; }
  void Reset() {
    level_known_ = false;
    high_level_ = false;
    pending_ = 0;
    overflowed_ = false;
  }

  bool configured() const { return configured_; }
  bool level_known() const { return level_known_; }
  bool high() const { return level_known_ && high_level_; }
  uint16_t pending() const { return pending_; }
  uint16_t capacity() const { return capacity_; }
  bool overflowed() const { return overflowed_; }

 private:
  bool Enqueue() {
    if (pending_ == capacity_) {
      overflowed_ = true;
      return false;
    }
    ++pending_;
    return true;
  }

  Sample low_;
  Sample high_;
  uint16_t capacity_;
  HighAcquisitionPolicy policy_;
  bool configured_;
  bool level_known_;
  bool high_level_;
  uint16_t pending_;
  bool overflowed_;
};

}  // namespace eurorack_patterns

#endif  // EURORACK_PATTERNS_EVENTS_H_
