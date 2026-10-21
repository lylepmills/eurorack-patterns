// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "../examples/daisy/bench.h"
#include "../examples/daisy/experiment.h"
#include <cstdio>
#include <cstdlib>
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)

static void InterruptedPress(uint32_t scenario) {
  bench::Controls controls; controls.Reset(250, false);
  bench::Experiment experiment(scenario, false);
  unsigned taps = 0, holds = 0, invalid = 0, gaps = 0;
  for (uint32_t us = 0; us < 2000000; us += 1000) {
    if (experiment.Stall(us)) { us += 25000; experiment.EndStall(us); }
    const bool pressed = (us >= 100000 && us < (scenario == bench::kReleaseStall ? 250000u : 900000u)) ||
                         (us >= 1200000 && us < 1300000);
    const bool valid = !experiment.InvalidAdc(us);
    const auto external = experiment.Observe(us, 0, valid, pressed);
    const auto r = controls.Step(us, 0, valid, pressed, external);
    taps += r.gesture == 1; holds += r.gesture == 2;
    invalid += !valid; gaps += !r.cadence_valid;
    if (scenario != bench::kPressAdcGap && us < 1310000) CHECK(r.actions == 0);
  }
  CHECK(taps == 1 && holds == (scenario == bench::kPressAdcGap ? 1u : 0u));
  CHECK(invalid == (scenario == bench::kPressAdcGap ? 250u : 0u));
  CHECK(gaps == (scenario == bench::kPressAdcGap ? 0u : 1u));
  CHECK(experiment.stimulus().trigger >= 0 && experiment.stimulus().end >= 0);
}
static void MissingCrossing(bool up) {
  bench::Controls controls; controls.Reset(250, false);
  bench::Experiment experiment(up ? bench::kPickupGapUp : bench::kPickupGapDown, false);
  unsigned invalid = 0;
  for (uint32_t us = 0; us < 2000000; us += 1000) {
    // Cross the trigger threshold at 100 ms, then the target inside the gap.
    uint16_t raw = up ? 0 : 65535;
    if (us >= 100000) raw = up ? 10000 : 22000;
    if (us >= 200000) raw = up ? 40000 : 5000;
    if (us >= 1500000) raw = up ? 5000 : 40000; // A new observed crossing recovers.
    const bool valid = !experiment.InvalidAdc(us);
    if (!valid) raw = 0;
    const auto external = experiment.Observe(us, raw, valid, false);
    const auto r = controls.Step(us, raw, valid, false, external);
    invalid += !valid;
    if (us < 1500000) CHECK(r.state == 1 && !r.changed && r.value_ppm == 250000);
    else CHECK(r.state == 2);
  }
  CHECK(invalid == 1000);
}
int main() {
  for (uint32_t scenario = bench::kPressStall; scenario <= bench::kPressAdcGap; ++scenario)
    InterruptedPress(scenario);
  MissingCrossing(true); MissingCrossing(false);
  for (uint32_t scenario = bench::kPressStall; scenario <= bench::kPressAdcGap; ++scenario) {
    for (uint32_t delay : {1u, 8000u, 10000u, 12000u, 608000u, 610000u, 612000u, 1000000u}) {
      bench::Experiment timed(scenario, false, delay);
      timed.Observe(100000, 0, true, true);
      const uint32_t trigger = scenario == bench::kReleaseStall ? 200000 : 100000;
      if (scenario == bench::kReleaseStall) timed.Observe(trigger, 0, true, false);
      CHECK(timed.stimulus().trigger == int32_t(trigger));
      if (scenario == bench::kPressAdcGap) {
        CHECK(!timed.InvalidAdc(trigger+delay-1));
        CHECK(timed.InvalidAdc(trigger+delay));
        CHECK(!timed.InvalidAdc(trigger+delay+250000));
      } else {
        CHECK(timed.Stall(trigger+delay-1) == 0);
        CHECK(timed.Stall(trigger+delay) == 25);
        timed.EndStall(trigger+delay+25000);
        CHECK(timed.Stall(trigger+delay+26000) == 0);
      }
      CHECK(timed.stimulus().begin == int32_t(trigger+delay));
    }
  }
  // A short tap is still actionable while only the ADC is unavailable.
  bench::Controls c; c.Reset(250, false);
  bench::Experiment adc(bench::kPressAdcGap, false);
  for (uint32_t us = 0; us <= 500000; us += 1000) {
    const bool pressed = us >= 100000 && us < 200000;
    const bool valid = !adc.InvalidAdc(us);
    adc.Observe(us, 0, valid, pressed);
    const auto r = c.Step(us, 0, valid, pressed);
    CHECK(r.actions == (us >= 210000 ? 1u : 0u));
    if (r.gesture) CHECK(!valid && r.gesture == 1);
  }
  // A target edit during owned movement rearms pickup before this sample applies.
  c.Reset(250, false);
  bench::Experiment target(bench::kMovingTarget, false);
  for (uint32_t us = 0; us < 1000000; us += 1000) {
    const uint16_t raw = us < 100000 ? 0 : us < 200000 ? 20000 : us < 300000 ? 35000 : 50000;
    const auto edit = target.Observe(us, raw, true, false);
    const auto r = c.Step(us, raw, true, false, edit);
    if (us == 200000) CHECK(edit == 750 && r.state == 1 && r.value_ppm == 750000 && !r.changed);
    if (us >= 300000) CHECK(r.state == 2);
  }
  // Held-at-start is not a fresh edge; a new press is required to trigger a fault.
  bench::Experiment held(bench::kPressStall, true);
  held.Observe(0, 0, true, true); held.Observe(900000, 0, true, false);
  CHECK(held.stimulus().trigger == -1 && held.Stall(1000000) == 0);
  held.Observe(1100000, 0, true, true);
  CHECK(held.Stall(1199999) == 0 && held.Stall(1200000) == 25 && held.Stall(1300000) == 0);
  // Invalid ADC observations cannot arm a movement trigger from stale history.
  bench::Experiment movement(bench::kPickupGapUp, false);
  movement.Observe(0, 0, true, false);
  movement.Observe(1000, 0, false, false);
  movement.Observe(2000, 20000, true, false);
  CHECK(movement.stimulus().trigger == -1);
  std::puts("PASS: event-driven fault timing, cancellation, independent validity, missing crossings and target rearm (synthetic)");
}
