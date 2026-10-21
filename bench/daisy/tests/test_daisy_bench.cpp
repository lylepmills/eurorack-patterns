// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "../examples/daisy/bench.h"
#include <cstdio>
#include <cstdlib>
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)
int main() {
  bench::Controls c;
  c.Reset(500, false);
  auto r = c.Step(0, 10000, true, false);
  CHECK(r.state == 1 && r.value_ppm == 500000);
  r = c.Step(1000, 0, false, false);
  CHECK(r.accepted_ppm == -1 && !r.changed);
  r = c.Step(2000, 50000, true, false);
  CHECK(r.state == 1 && !r.changed); // Never infer a crossing over invalid data.
  r = c.Step(3000, 10000, true, false);
  CHECK(r.state == 2 && r.changed);
  c.Reset(500, false);
  c.Step(0, 10000, true, false);
  r = c.Step(11000, 50000, true, false);
  CHECK(!r.cadence_valid && r.state == 1 && !r.changed);
  // Exactly 10 ms is still continuous; greater than it is not.
  c.Reset(500, false); c.Step(0, 10000, true, false);
  CHECK(c.Step(10000, 50000, true, false).state == 2);
  // Bounce then one tap. Startup and press qualification must not emit a tap.
  c.Reset(250, false);
  for (unsigned ms = 0; ms <= 100; ++ms) {
    const bool pressed = (ms >= 10 && ms < 12) || (ms >= 14 && ms < 50);
    r = c.Step(ms * 1000, 0, true, pressed);
    CHECK(r.actions == (ms >= 60 ? 1u : 0u));
  }
  CHECK(r.target_ppm == 750000);
  // Hold fires once and consumes release; a subsequent tap is independent.
  c.Reset(250, false);
  for (unsigned ms = 0; ms <= 1100; ++ms) {
    r = c.Step(ms * 1000, 0, true, ms >= 1 && ms < 900);
    CHECK(r.actions == (ms >= 611 ? 1u : 0u));
    if (ms == 611) CHECK(r.gesture == 2 && r.target_ppm == 500000);
  }
  // A startup-held button cannot trigger either action, including on release.
  c.Reset(250, true);
  for (unsigned ms = 0; ms <= 1000; ++ms)
    CHECK(c.Step(ms * 1000, 0, true, ms < 800).actions == 0);
  // A service gap during a press cancels ownership, including a later release.
  c.Reset(250, false);
  for (unsigned ms = 0; ms <= 100; ++ms) c.Step(ms * 1000, 0, true, ms >= 1);
  for (unsigned ms = 200; ms <= 1000; ++ms)
    CHECK(c.Step(ms * 1000, 0, true, ms < 900).actions == 0);
  bench::Schedule schedule;
  CHECK(schedule.Due(0) && schedule.Take(0) == 0);
  CHECK(!schedule.Due(999) && schedule.Take(1000) == 0);
  CHECK(schedule.Take(27000) == 25 && !schedule.Due(27999));
  bench::Clock clock(0xfffffff0u, 240000000);
  CHECK(clock.Us(224) == 1); // Raw counter wrap before unit conversion.
  CHECK(clock.Us(480224) == 2001);
  bench::Clock full_window(0, 240000000);
  for (uint64_t ms = 0; ms <= bench::kMaxDurationMs; ++ms)
    CHECK(full_window.Us(uint32_t(ms * 240000)) == ms * 1000);
  bench::Clock non_integer(100, 240500000);
  CHECK(non_integer.Us(240500100) == 1000000);
  std::puts("PASS: Daisy adapter pickup, gesture, gap, scheduler and timer boundaries (synthetic)");
}
