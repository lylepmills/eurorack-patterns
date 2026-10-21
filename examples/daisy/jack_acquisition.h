// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EP_DAISY_JACK_ACQUISITION_H_
#define EP_DAISY_JACK_ACQUISITION_H_
#include "jack_bench.h"

namespace jackbench {
// Publication must be atomic with respect to acquisition. A strictly future
// boundary includes a slot already driven at the exact request microsecond.
inline uint32_t ScheduledFinishLimit(const Plan& plan, uint32_t request_us) {
  const uint32_t minimum = plan.fault ? 3000000u : 1000000u;
  uint32_t limit = (request_us / kPeriodUs + 1) * kPeriodUs;
  if (limit < minimum) limit = minimum;
  if (limit > plan.duration_ms * 1000) limit = plan.duration_ms * 1000;
  return limit;
}
// One outstanding conversion. Timer and ADC handlers must have the same
// preemption priority. No polling, catch-up burst, or reused ADC result.
class Acquisition {
 public:
  enum class Action { kNone, kDrive, kSample, kTimeout, kFinished };
  explicit Acquisition(const Plan& plan) : plan_(plan), detector_(plan.policy), fault_(plan) {}
  Action Next(uint32_t us, uint32_t limit) {
    if (phase_ == 2) return us - record.sample_us >= kPeriodUs ? Action::kTimeout : Action::kNone;
    if (phase_ == 1) {
      if (us - record.drive_us < kSettleUs) return Action::kNone;
      record.sample_us = us; phase_ = 2; return Action::kSample;
    }
    if (us >= limit) return Action::kFinished;
    // Fault 2 explicitly suspends acquisition, not the foreground. Audio and
    // the timer continue; the first recovered observation carries the gap.
    if (!fault_begin && fault_.PauseDue(us)) fault_begin = us;
    if (plan_.fault == 2 && fault_begin && !fault_end) {
      if (us - fault_begin < plan_.fault_us) return Action::kNone;
      fault_end = us;
    }
    if (!schedule_.Due(us)) return Action::kNone;
    record = {}; record.seq = count; record.drive_us = us;
    record.slot = us / kPeriodUs; record.probe = probe_.Next();
    skipped_ = schedule_.Take(us); missed += skipped_; record.missed = missed;
    phase_ = 1; return Action::kDrive;
  }
  void Converted(uint16_t raw, bool valid, uint32_t us) {
    record.raw = raw; record.adc_valid = valid; record.adc_end_us = us;
    failures += !valid;
    if (fault_.Inject(record.sample_us)) {
      record.injected = 1;
      if (!fault_begin) fault_begin = record.sample_us;
    } else if (plan_.fault == 1 && fault_begin && !fault_end) fault_end = record.sample_us;
    detector_.Observe(record, skipped_ != 0);
  }
  void Finished(uint32_t us) {
    record.end_us = us; fault_.Observe(record, detector_); ++count; phase_ = 0;
  }
  const FaultTiming& fault() const { return fault_; }
  Record record{};
  uint32_t count = 0, missed = 0, failures = 0, fault_begin = 0, fault_end = 0;
 private:
  Plan plan_;
  Probe probe_;
  Schedule schedule_;
  Detector detector_;
  FaultTiming fault_;
  uint32_t skipped_ = 0, phase_ = 0;
};
} // namespace jackbench
#endif
