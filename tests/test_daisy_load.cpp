// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "../examples/daisy/load.h"
#include <cstdio>
#include <cstdlib>
#include <type_traits>
static_assert(std::is_trivial<bench::Bucket>::value, "No pre-initialization SDRAM constructors");
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)
static void Feed(bench::Traffic& t, uint32_t seq, bool good = true) {
  uint8_t frame[64] = {0xa5};
  for (unsigned i = 0; i < 4; ++i) frame[1+i] = uint8_t(seq >> (8*i));
  for (unsigned i = 5; i < 63; ++i) frame[i] = uint8_t(seq+i);
  frame[63] = good ? 0x5a : 0;
  for (auto b : frame) CHECK(t.Feed(b, true));
}
int main() {
  bench::Workload w;
  CHECK(!w.Valid()); w.duration = 150000; CHECK(w.Valid());
  w.duration += 1000; CHECK(!w.Valid()); w.mode = 1; CHECK(w.Valid());
  w.duration = bench::kMaxSoakMs; CHECK(w.Valid());
  ++w.duration; CHECK(!w.Valid()); --w.duration;
  w.audio_permille = 701; CHECK(!w.Valid()); w.audio_permille = 700;
  w.block = 17; CHECK(!w.Valid()); w.block = 16;
  w.usb_hz = 500; CHECK(w.Valid()); w.usb_hz = 501; CHECK(!w.Valid());
  bench::Traffic t;
  CHECK(!t.Feed('?', false));
  Feed(t, 0xffffffffu); Feed(t, 0); // wrapping sequence is contiguous
  CHECK(t.counters().packets == 2 && !t.counters().sequence_errors);
  Feed(t, 2); Feed(t, 3, false);
  CHECK(t.counters().packets == 3 && t.counters().bytes == 256);
  CHECK(t.counters().sequence_errors == 1 && t.counters().malformed == 1);
  t.ResetCounters(); CHECK(!t.counters().packets);
  // A partial packet at the measurement boundary stays traffic; it does not
  // leak payload bytes into the command mailbox or count as a complete packet.
  CHECK(t.Feed(0xa5, true));
  t.ResetCounters();
  for (unsigned i = 1; i < 64; ++i) CHECK(t.Feed('R', true));
  CHECK(!t.counters().bytes && !t.Feed('\n', false));
  Feed(t, 42); CHECK(t.counters().packets == 1 && !t.counters().sequence_errors);
  bench::Bucket b; b.Reset();
  bench::Controls c; c.Reset(250, false);
  bench::Record r{0, 100, 35, 40, 1234, 1, 0, 0, -1, c.Step(100, 1234, true, false), 0};
  b.Add(r, 0, 0);
  r.time_us = 12100; r.work_us = 500; r.adc_valid = 0;
  r.result = c.Step(12100, 0, false, false); b.Add(r, 11, 12000);
  CHECK(b.count == 2 && b.first_us == 100 && b.last_us == 12100 && b.missed == 11);
  CHECK(b.failures == 1 && b.cadence_breaks == 1 && b.max_work_us == 500 && b.max_interval_us == 12000);
  CHECK(b.raw_min == 1234 && b.raw_max == 1234 && !b.actions);
  // One-hour scheduling and timer extension cross many raw hardware wraps.
  bench::Clock clock(0, 240000000);
  bench::Schedule schedule;
  for (uint32_t second = 0; second < 3600; ++second) {
    uint32_t us = clock.Us(uint32_t(uint64_t(second)*240000000));
    CHECK(us == second*1000000 && schedule.Due(us));
    CHECK(schedule.Take(us) == (second ? 999u : 0u));
  }
  std::puts("PASS: load bounds, USB framing/counters, continuous aggregates and one-hour timer wrap");
}
