// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
// Synthetic tick replays; they do not establish electrical or ISR timing.
#include <eurorack_patterns/trigger_delay.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <map>

using eurorack_patterns::TriggerDelay;

#define CHECK(condition) do { if (!(condition)) { \
  std::fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
  std::exit(1); } } while (0)

static void SourceIdentityCounterexample() {
  TriggerDelay<3> delay;
  CHECK(delay.Schedule(0x1u, 3));  // A at tick 0.
  CHECK(delay.Tick() == 0);
  CHECK(delay.Schedule(0x2u, 3));  // B at tick 1, while A waits.
  CHECK(delay.Tick() == 0);
  CHECK(delay.Tick() == 0);
  CHECK(delay.Tick() == 0x1u);
  CHECK(delay.Tick() == 0x2u);
  CHECK(delay.Tick() == 0);
}

static void DeadlinesAndCoalescence() {
  TriggerDelay<5> delay;
  CHECK(delay.Schedule(0x1u, 4));
  CHECK(delay.Tick() == 0);
  CHECK(delay.Schedule(0x1u, 1));
  CHECK(delay.Tick() == 0);
  CHECK(delay.Tick() == 0x1u);  // A at tick 2, from the later request.
  CHECK(delay.Tick() == 0);
  CHECK(delay.Tick() == 0x1u);  // A at tick 4, original deadline retained.

  delay.Reset();
  CHECK(delay.Schedule(0x1u, 3));
  CHECK(delay.Schedule(0x1u, 3));  // Identical channel/deadline coalesces.
  CHECK(delay.Schedule(0x80000000u, 3));
  CHECK(delay.Tick() == 0);
  CHECK(delay.Schedule(0x1u, 2));  // Same A deadline from a later tick.
  CHECK(delay.Tick() == 0);
  CHECK(delay.Tick() == 0);
  CHECK(delay.Tick() == 0x80000001u);
  CHECK(delay.Tick() == 0);

  delay.Reset();
  CHECK(delay.Schedule(0x80000001u, 0));
  CHECK(delay.Tick() == 0x80000001u);
  CHECK(delay.Tick() == 0);
  CHECK(delay.Schedule(0u, 5));
  CHECK(delay.Tick() == 0);
}

static void BoundsResetAndWrap() {
  TriggerDelay<2> delay;
  const std::size_t* max_delay = &TriggerDelay<2>::kMaxDelayTicks;
  const std::size_t* buckets = &TriggerDelay<2>::kBucketCount;
  CHECK(*max_delay == 2 && *buckets == 3);
  CHECK(delay.Schedule(0x1u, 2));
  CHECK(!delay.Schedule(0x2u, 3));  // Reject without disturbing A.
  CHECK(delay.Tick() == 0);
  CHECK(delay.Tick() == 0);
  CHECK(delay.Tick() == 0x1u);
  CHECK(delay.Tick() == 0);  // Head wraps around a three-bucket ring.

  CHECK(delay.Schedule(0x2u, 2));
  CHECK(delay.Tick() == 0);
  delay.Reset();
  CHECK(delay.Tick() == 0);
  CHECK(delay.Tick() == 0);
  CHECK(delay.Tick() == 0);
  CHECK(delay.Schedule(0x4u, 0));
  CHECK(delay.Tick() == 0x4u);

  TriggerDelay<0> immediate;
  CHECK(immediate.Schedule(0x80000000u, 0));
  CHECK(!immediate.Schedule(0x1u, 1));
  CHECK(immediate.Tick() == 0x80000000u);
  CHECK(immediate.Tick() == 0);
}

static uint32_t Next(uint32_t& state) {
  state = state * 1664525u + 1013904223u;
  return state;
}

static void AbsoluteDeadlineOracle() {
  // A map keyed by absolute tick deliberately models deadlines without a
  // circular buffer. Each mask is an OR of events due at that absolute tick.
  TriggerDelay<7> delay;
  std::map<unsigned, uint32_t> due;
  uint32_t rng = 0x54444c31u;
  for (unsigned tick = 0; tick < 2000; ++tick) {
    if (tick == 617 || tick == 1379) {
      delay.Reset();
      due.clear();
    }
    const unsigned requests = Next(rng) >> 30;
    for (unsigned request = 0; request < requests; ++request) {
      const std::size_t wait = (Next(rng) >> 16) % 10;
      const uint32_t bits = (uint32_t(1) << ((Next(rng) >> 16) % 32)) |
                            (uint32_t(1) << ((Next(rng) >> 16) % 32));
      const bool accepted = delay.Schedule(bits, wait);
      CHECK(accepted == (wait <= 7));
      if (accepted) due[tick + static_cast<unsigned>(wait)] |= bits;
    }
    const std::map<unsigned, uint32_t>::iterator expected = due.find(tick);
    const uint32_t mask = expected == due.end() ? 0 : expected->second;
    CHECK(delay.Tick() == mask);
    if (expected != due.end()) due.erase(expected);
  }
}

int main() {
  SourceIdentityCounterexample();
  DeadlinesAndCoalescence();
  BoundsResetAndWrap();
  AbsoluteDeadlineOracle();
  std::puts("PASS: trigger identity, deadlines, coalescence, bounds, reset, wrap");
}
