// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EP_DAISY_DIAGNOSTICS_H_
#define EP_DAISY_DIAGNOSTICS_H_
#include <cstdint>
#include <cstdio>

namespace bench {
// Optional bench instrumentation, not a library timing primitive. CPU timer
// reads bracket GPIO calls; external pad timing still needs a physical capture.
// Raw tick differences are modulo 2^32. Extended ticks are from Clock, before
// unit conversion, and permit an independent check of integer microseconds.
struct Timing {
  uint64_t begin_elapsed, end_elapsed;
  uint32_t seq, time_us, work_us;
  uint32_t begin_tick, rise_before, rise_after, end_tick, fall_before, fall_after;
};
enum TimingPeak {
  kIntervalUs, kWorkUs, kRiseIntervalTicks, kWidthTicks,
  kBeginGuardTicks, kEndGuardTicks, kRiseCallTicks, kFallCallTicks, kTimingPeaks
};
struct TimingPair { Timing previous, current; };
inline uint32_t TimingMetric(unsigned kind, const Timing& p, const Timing& t) {
  switch (kind) {
    case kIntervalUs: return t.seq ? t.time_us - p.time_us : 0;
    case kWorkUs: return t.work_us;
    case kRiseIntervalTicks: return t.seq ? t.rise_before - p.rise_before : 0;
    case kWidthTicks: return t.fall_before - t.rise_before;
    case kBeginGuardTicks: return t.rise_after - t.begin_tick;
    case kEndGuardTicks: return t.fall_after - t.end_tick;
    case kRiseCallTicks: return t.rise_after - t.rise_before;
    default: return t.fall_after - t.fall_before;
  }
}
struct TimingBucket {
  // POD in SDRAM: reset only after memory initialization. Ties retain the first
  // observation; a peak's predecessor may belong to the previous second.
  Timing first, last;
  TimingPair peak[kTimingPeaks];
  uint32_t count, max_bookkeeping_ticks, bookkeeping_seq;
  void Reset() { *this = {}; }
  void Add(const Timing& previous, const Timing& current) {
    if (!count) first = current;
    last = current;
    for (unsigned k = 0; k < kTimingPeaks; ++k) {
      if (!count || TimingMetric(k, previous, current) >
                    TimingMetric(k, peak[k].previous, peak[k].current))
        peak[k] = {previous, current};
    }
    ++count;
  }
  void Bookkeeping(uint32_t seq, uint32_t ticks) {
    if (ticks > max_bookkeeping_ticks) {
      max_bookkeeping_ticks = ticks; bookkeeping_seq = seq;
    }
  }
};
inline int FormatTiming(char* line, size_t size, uint32_t second, unsigned kind,
                        const Timing& p, const Timing& t) {
  return std::snprintf(line, size,
      "D,%u,%u,%llu,%llu,%u,%u,%u,%u,%u,%u,%u,%u,%u,"
      "%llu,%llu,%u,%u,%u,%u,%u,%u,%u,%u,%u\n",
      unsigned(second), kind,
      static_cast<unsigned long long>(p.begin_elapsed), static_cast<unsigned long long>(p.end_elapsed),
      unsigned(p.seq), unsigned(p.time_us), unsigned(p.work_us), unsigned(p.begin_tick),
      unsigned(p.rise_before), unsigned(p.rise_after), unsigned(p.end_tick),
      unsigned(p.fall_before), unsigned(p.fall_after),
      static_cast<unsigned long long>(t.begin_elapsed), static_cast<unsigned long long>(t.end_elapsed),
      unsigned(t.seq), unsigned(t.time_us), unsigned(t.work_us), unsigned(t.begin_tick),
      unsigned(t.rise_before), unsigned(t.rise_after), unsigned(t.end_tick),
      unsigned(t.fall_before), unsigned(t.fall_after));
}
} // namespace bench
#endif
