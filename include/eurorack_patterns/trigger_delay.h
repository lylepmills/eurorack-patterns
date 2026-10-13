// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EURORACK_PATTERNS_TRIGGER_DELAY_H_
#define EURORACK_PATTERNS_TRIGGER_DELAY_H_

#include <cstddef>
#include <cstdint>
#include <limits>

namespace eurorack_patterns {

// Delays a mask of up to 32 independent trigger inputs by caller-owned ticks.
// Schedule before Tick: delay zero is returned by that Tick, delay N by the
// Nth subsequent Tick. One bucket holds all input bits due at the same tick;
// repeated scheduling of one bit for the same deadline coalesces.
// Single owner only. Synchronize externally if calls cross execution contexts.
template <std::size_t MaxDelayTicks>
class TriggerDelay {
  static_assert(MaxDelayTicks <
                    std::numeric_limits<std::size_t>::max() / sizeof(uint32_t),
                "TriggerDelay bucket count or byte size would overflow");

 public:
  static const std::size_t kMaxDelayTicks = MaxDelayTicks;
  static const std::size_t kBucketCount = MaxDelayTicks + 1;

  TriggerDelay() : head_(0), buckets_() {}

  // Invalid delays leave all pending triggers unchanged. Zero mask is a valid
  // no-op. A true return means accepted, not that a distinct event was added.
  bool Schedule(uint32_t mask, std::size_t delay_ticks) {
    if (delay_ticks > MaxDelayTicks) return false;
    std::size_t target = head_ + delay_ticks;
    if (target >= kBucketCount) target -= kBucketCount;
    buckets_[target] |= mask;
    return true;
  }

  // Returns and clears the current bucket, then advances exactly one tick.
  uint32_t Tick() {
    const uint32_t due = buckets_[head_];
    buckets_[head_] = 0;
    if (++head_ == kBucketCount) head_ = 0;
    return due;
  }

  // Drops all pending triggers and returns to the initial tick position.
  void Reset() {
    for (std::size_t i = 0; i < kBucketCount; ++i) buckets_[i] = 0;
    head_ = 0;
  }

 private:
  std::size_t head_;
  uint32_t buckets_[kBucketCount];
};

// C++11 requires definitions when a consumer ODR-uses these public constants
// (for example by taking their address or passing one by const reference).
template <std::size_t MaxDelayTicks>
const std::size_t TriggerDelay<MaxDelayTicks>::kMaxDelayTicks;

template <std::size_t MaxDelayTicks>
const std::size_t TriggerDelay<MaxDelayTicks>::kBucketCount;

}  // namespace eurorack_patterns

#endif  // EURORACK_PATTERNS_TRIGGER_DELAY_H_
