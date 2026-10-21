// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EP_DAISY_JACK_BENCH_H_
#define EP_DAISY_JACK_BENCH_H_
#include <eurorack_patterns/presence.h>
#include "pulse_generator.h"
#include <cstdio>

// Measurement adapter, not a recommended electrical front end or universal
// insertion latency. A completed conversion must belong to this probe bit.
namespace jackbench {
constexpr uint32_t kPeriodUs = 500, kSettleUs = 150;
constexpr uint32_t kMaxDurationMs = 300000;
constexpr uint32_t kMaxRecords = kMaxDurationMs * 1000 / kPeriodUs;
constexpr uint16_t kLow = 16384, kHigh = 49151;
struct Plan {
  uint32_t token = 0, duration_ms = 0, fault = 0, policy = 1;
  // 0: elapsed time; 1/4: first insertion/removal evidence; 2/5: before
  // candidate qualification; 3/6: after published insertion/removal.
  uint32_t trigger = 0, delay_slots = 0, fault_us = 25000;
  // Zero block disables audio. Stop at least one second before the acquisition
  // limit, leaving a complete unloaded tail and explicit recovery evidence.
  uint32_t audio_block = 0, audio_permille = 0, audio_off_ms = 0;
  bool Valid() const {
    return duration_ms >= 1000 && duration_ms <= kMaxDurationMs &&
           fault <= 2 && policy <= 1 && (!fault || duration_ms >= 3000) &&
           trigger <= 6 && delay_slots <= 64 && fault_us >= 500 &&
           fault_us <= 100000 && fault_us % kPeriodUs == 0 &&
           (trigger || delay_slots == 0) && (!trigger || (fault && policy == 1)) &&
           (fault || fault_us == 25000) &&
           ((!audio_block && !audio_permille && !audio_off_ms) ||
            ((audio_block == 16 || audio_block == 48 || audio_block == 96) &&
             audio_permille <= 700 && audio_off_ms >= 1000 &&
             audio_off_ms <= duration_ms - 1000));
  }
};
inline bool Parse(const char* p, Plan& out) {
  Plan q;
  if (*p++ != 'J' || *p++ != ',' || !pulsegen::Number(p, q.token) ||
      *p++ != ',' || !pulsegen::Number(p, q.duration_ms) ||
      *p++ != ',' || !pulsegen::Number(p, q.fault) ||
      *p++ != ',' || !pulsegen::Number(p, q.policy)) return false;
  if (*p && (*p++ != ',' || !pulsegen::Number(p, q.trigger) ||
      *p++ != ',' || !pulsegen::Number(p, q.delay_slots) ||
      *p++ != ',' || !pulsegen::Number(p, q.fault_us))) return false;
  if (*p && (*p++ != ',' || !pulsegen::Number(p, q.audio_block) ||
      *p++ != ',' || !pulsegen::Number(p, q.audio_permille) ||
      *p++ != ',' || !pulsegen::Number(p, q.audio_off_ms))) return false;
  if (*p || !q.Valid()) return false;
  out = q; return true;
}
// USB IRQ owns Feed(); reset and inspection by the main loop require the IRQ
// guard. Only the exact token-bound finish command is harmless while busy.
class FinishCommand {
 public:
  enum class Result { kPartial, kComplete, kInvalid };
  void Reset(uint32_t token) {
    size_ = static_cast<size_t>(std::snprintf(expected_, sizeof(expected_), "JF,%u\n", unsigned(token)));
    used_ = 0; bad_ = false;
  }
  Result Feed(char c) {
    if (bad_ || c != expected_[used_]) { bad_ = true; return Result::kInvalid; }
    if (++used_ == size_) { used_ = 0; return Result::kComplete; }
    return Result::kPartial;
  }
  bool Incomplete() const { return bad_ || used_ != 0; }
 private:
  char expected_[16]{};
  size_t size_ = 0, used_ = 0;
  bool bad_ = false;
};
inline uint32_t FinishLimit(const Plan& plan, uint32_t request_us) {
  const uint32_t minimum = plan.fault ? 3000000u : 1000000u;
  uint32_t limit = ((request_us + kPeriodUs - 1) / kPeriodUs) * kPeriodUs;
  if (limit < minimum) limit = minimum;
  if (limit > plan.duration_ms * 1000) limit = plan.duration_ms * 1000;
  return limit;
}
class Probe {
 public:
  bool Next() {
    const bool bit = (state_ & 1u) != 0;
    state_ = static_cast<uint16_t>((state_ >> 1) ^ (bit ? 0xb400u : 0u));
    return bit;
  }
 private:
  uint16_t state_ = 0xace1;
};
// Never compress missed observations into a burst of catch-up work.
class Schedule {
 public:
  bool Due(uint32_t us) const { return us / kPeriodUs >= next_; }
  uint32_t Take(uint32_t us) {
    const uint32_t slot = us / kPeriodUs, skipped = slot - next_;
    next_ = slot + 1; return skipped;
  }
 private:
  uint32_t next_ = 0;
};
struct Record {
  uint32_t seq, slot, drive_us, sample_us, adc_end_us, end_us, missed, windows;
  uint16_t raw, last_mismatches, bad_windows;
  uint8_t probe, adc_valid, injected, evidence, window_done, ready, patched;
};
inline eurorack_patterns::PresenceEvidence Evidence(const Record& r, bool gap) {
  using E = eurorack_patterns::PresenceEvidence;
  if (gap || !r.adc_valid || r.injected ||
      r.sample_us < r.drive_us + kSettleUs ||
      r.adc_end_us >= (r.slot + 1) * kPeriodUs ||
      (r.raw > kLow && r.raw < kHigh)) return E::kInvalid;
  return bool(r.raw >= kHigh) == bool(r.probe) ? E::kMatch : E::kMismatch;
}
class Detector {
 public:
  explicit Detector(uint32_t policy) {
    using P = eurorack_patterns::PresenceStartupPolicy;
    state_.Configure({64, 3, 8, policy ? P::kRequireStreak : P::kFirstWindowDecides}, {false, false});
  }
  void Observe(Record& r, bool gap) {
    const auto e = Evidence(r, gap);
    r.evidence = static_cast<uint8_t>(e);
    r.window_done = state_.Observe(e);
    r.ready = state_.ready(); r.patched = state_.patched();
    r.windows = state_.windows(); r.last_mismatches = state_.last_mismatches();
    r.bad_windows = state_.bad_windows();
  }
  uint16_t observations() const { return state_.observations(); }
  uint16_t mismatches() const { return state_.mismatches(); }
 private:
  eurorack_patterns::PresenceDetector state_;
};
// One fault per commanded acquisition. Triggering observes real evidence; it
// never fabricates a probe/sample or resets the detector. The next slot is the
// earliest fault boundary, so no completed observation is changed retroactively.
class FaultTiming {
 public:
  explicit FaultTiming(const Plan& plan) : plan_(plan) {
    armed_ = plan.fault && !plan.trigger;
    due_us_ = armed_ ? 2000000u : 0u;
  }
  void Observe(const Record& r, const Detector& detector) {
    bool event = false;
    if (plan_.fault && plan_.trigger && !armed_) {
      const bool empty = seen_empty_ && r.ready && !r.patched;
      const bool inserted = seen_patched_ && r.ready && r.patched;
      switch (plan_.trigger) {
        case 1: event = empty && r.evidence == 1; break;
        case 2: event = empty && r.bad_windows == 7 &&
            detector.observations() == 63 && detector.mismatches() >= 3; break;
        case 3: event = seen_empty_ && r.ready && r.patched && !previous_patched_; break;
        case 4: event = inserted && r.evidence == 0 && r.probe; break;
        case 5: event = inserted && detector.observations() == 63 &&
            detector.mismatches() < 3; break;
        case 6: event = seen_patched_ && r.ready && !r.patched && previous_patched_; break;
        default: break;
      }
    }
    if (event) {
      armed_ = true; event_seq_ = r.seq; event_us_ = r.end_us;
      due_us_ = (r.slot + 1 + plan_.delay_slots) * kPeriodUs;
    }
    seen_empty_ |= r.ready && !r.patched;
    seen_patched_ |= seen_empty_ && r.ready && r.patched;
    previous_patched_ = r.ready && r.patched;
  }
  bool PauseDue(uint32_t us) const { return armed_ && plan_.fault == 2 && us >= due_us_; }
  bool Inject(uint32_t sample_us) const {
    return armed_ && plan_.fault == 1 && sample_us >= due_us_ &&
           sample_us - due_us_ < plan_.fault_us;
  }
  uint32_t event_seq() const { return event_seq_; }
  uint32_t event_us() const { return event_us_; }
  uint32_t due_us() const { return due_us_; }
 private:
  Plan plan_;
  bool armed_ = false, seen_empty_ = false, seen_patched_ = false, previous_patched_ = false;
  uint32_t event_seq_ = UINT32_MAX, event_us_ = 0, due_us_ = 0;
};
constexpr const char* kColumns = "seq,slot,drive_us,sample_us,adc_end_us,end_us,missed,windows,raw,last_mismatches,bad_windows,probe,adc_valid,injected,evidence,window_done,ready,patched";
inline int Format(char* out, size_t n, const Record& r) {
  return std::snprintf(out, n, "JDATA,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u\n",
    unsigned(r.seq), unsigned(r.slot), unsigned(r.drive_us), unsigned(r.sample_us),
    unsigned(r.adc_end_us), unsigned(r.end_us), unsigned(r.missed), unsigned(r.windows),
    unsigned(r.raw), unsigned(r.last_mismatches), unsigned(r.bad_windows), unsigned(r.probe),
    unsigned(r.adc_valid), unsigned(r.injected), unsigned(r.evidence), unsigned(r.window_done),
    unsigned(r.ready), unsigned(r.patched));
}
} // namespace jackbench
#endif
