// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EP_DAISY_LOAD_H_
#define EP_DAISY_LOAD_H_
#include "bench.h"
#include "experiment.h"
#include <algorithm>
#include <cstddef>

namespace bench {
constexpr uint32_t kMaxSoakMs = 3600000;
constexpr uint32_t kMaxBuckets = kMaxSoakMs / 1000;
struct Workload {
  uint32_t mode = 0, duration = 0, target = 250, block = 48, usb_hz = 0;
  uint32_t scenario = kManual, fault_delay_us = 0; // Zero retains legacy schedules.
  int32_t audio_permille = -1; // -1: stopped; 0: DMA callback without padding.
  bool Valid() const {
    return (!fault_delay_us || (!mode && scenario >= kPressStall && scenario <= kPressAdcGap &&
                                fault_delay_us <= 1000000)) &&
      mode <= 2 && duration >= 1000 && duration % 1000 == 0 &&
      duration <= (mode ? kMaxSoakMs : kMaxDurationMs) && target <= 1000 &&
      audio_permille >= -1 && audio_permille <= 700 &&
      (block == 16 || block == 48 || block == 96) &&
      (usb_hz == 0 || usb_hz == 100 || usb_hz == 500) &&
      (scenario == kManual || (!mode && scenario >= kPressStall && scenario <= kPickupGapDown &&
                              (scenario < kPickupGapUp || target == 250)));
  }
};

// Each valid frame is exactly 64 bytes. USB receive callbacks may split or
// combine frames; framing is independent of those delivery boundaries. Traffic
// bytes cannot become commands, including packets finishing after a capture.
class Traffic {
 public:
  struct Counters { uint32_t packets = 0, bytes = 0, malformed = 0, sequence_errors = 0; };
  bool Feed(uint8_t byte, bool measuring) {
    if (!used_ && byte != 0xa5) return false;
    if (!used_) include_ = measuring;
    include_ = include_ && measuring;
    frame_[used_++] = byte;
    if (used_ != sizeof(frame_)) return true;
    used_ = 0;
    if (!include_) return true;
    counters_.bytes += sizeof(frame_);
    uint32_t seq = 0;
    for (unsigned i = 0; i < 4; ++i) seq |= uint32_t(frame_[1+i]) << (8*i);
    bool valid = frame_[63] == 0x5a;
    for (unsigned i = 5; i < 63; ++i) valid = valid && frame_[i] == uint8_t(seq+i);
    if (!valid) { ++counters_.malformed; return true; }
    if (have_ && seq != previous_ + 1) ++counters_.sequence_errors;
    have_ = true; previous_ = seq; ++counters_.packets;
    return true;
  }
  void ResetCounters() { counters_ = {}; have_ = false; include_ = false; }
  Counters counters() const { return counters_; }
 private:
  uint8_t frame_[64]{};
  size_t used_ = 0;
  bool include_ = false, have_ = false;
  uint32_t previous_ = 0;
  Counters counters_;
};

// Continuous control service, bounded storage. A bucket is an aggregate, not a
// replayable trace. Empty seconds remain explicit and are never fabricated.
struct Bucket {
  // POD storage: SDRAM must not be touched by constructors before its init.
  uint32_t count, first_us, last_us, missed, failures;
  uint32_t cadence_breaks, actions, max_work_us, max_interval_us;
  uint32_t raw_min, raw_max;
  void Reset() { *this = {}; raw_min = 65535; }
  void Add(const Record& r, uint32_t skipped, uint32_t interval) {
    if (!count) first_us = r.time_us;
    ++count; last_us = r.time_us; missed += skipped;
    failures += !r.adc_valid;
    cadence_breaks += !r.result.cadence_valid;
    actions += r.result.gesture != 0;
    max_work_us = std::max(max_work_us, r.work_us);
    max_interval_us = std::max(max_interval_us, interval);
    if (r.adc_valid) { raw_min = std::min(raw_min, r.raw); raw_max = std::max(raw_max, r.raw); }
  }
};
} // namespace bench
#endif
