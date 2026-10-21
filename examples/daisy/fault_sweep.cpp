// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
// Deterministic host campaign for the adapter's boundary contracts. This uses
// virtual observations; it does not measure physical edges or interrupt load.
#include "bench.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

static uint32_t cases = 0, pending_press_cases = 0;
static bool csv = false;
static uint32_t AtOrAfter(uint32_t t, uint32_t phase) {
  return ((t-phase+999)/1000)*1000+phase;
}
static void Check(bool ok, const char* name, uint32_t input_phase,
                  uint32_t service_phase, int offset, const char* what) {
  if (ok) return;
  std::fprintf(stderr, "FAIL %s input=%u service=%u offset=%d: %s\n",
               name, unsigned(input_phase), unsigned(service_phase), offset, what);
  std::exit(1);
}

static void Button(const char* name, unsigned kind, uint32_t ip, uint32_t sp, int offset) {
  // The expected boundary is calculated from the input timetable and the
  // declared 10 ms qualification / 600 ms hold contract, before running Step.
  const uint32_t press = 100000+ip, release = (kind == 2 || kind == 3 ? 300000u : 900000u)+ip;
  const uint32_t qualified_press = AtOrAfter(press, sp)+10000;
  const uint32_t boundary = kind == 0 ? qualified_press :
      kind == 1 ? qualified_press+600000 : AtOrAfter(release, sp)+10000;
  const uint32_t fault_begin = uint32_t(int64_t(boundary)+offset), fault_end = fault_begin+25000;
  const bool adc_only = kind == 3;
  // Before press qualification there is no owned role to cancel. The adapter
  // currently restarts debounce and can accept the still-held press afterward.
  // Preserve this counterexample explicitly instead of calling it cancellation.
  const bool pending = kind == 0 && fault_begin <= qualified_press;
  const unsigned first_expected = (adc_only || pending || (kind != 0 && fault_begin > boundary)) ? 1u : 0u;
  bench::Controls c; c.Reset(250, false);
  unsigned taps = 0, holds = 0, cadence_breaks = 0;
  for (uint32_t us = sp; us < 1600000; us += 1000) {
    const bool inside = fault_begin <= us && us < fault_end;
    if (inside && !adc_only) continue;
    const bool pressed = (press <= us && us < release) ||
                         (1200000+ip <= us && us < 1300000+ip);
    const auto r = c.Step(us, 0, !inside, pressed);
    taps += r.gesture == 1; holds += r.gesture == 2;
    cadence_breaks += !r.cadence_valid;
  }
  Check(cadence_breaks == (adc_only ? 0u : 1u), name, ip, sp, offset, "cadence accounting");
  Check(taps == 1+(kind >= 2 ? first_expected : 0u), name, ip, sp, offset, "tap count including fresh recovery tap");
  Check(holds == (kind < 2 ? first_expected : 0u), name, ip, sp, offset, "hold count / no duplicate release action");
  ++cases; pending_press_cases += pending;
  if (csv) std::printf("%s,%u,%u,%d,%u,%u,%u,%s\n", name, unsigned(ip), unsigned(sp), offset,
                       taps, holds, cadence_breaks, pending ? "pending_press_requalifies" : "contract");
}

static void Pickup(bool up, uint32_t ip, uint32_t sp, int offset) {
  const char* name = up ? "pickup_up" : "pickup_down";
  const uint32_t crossing = 150000+ip, return_time = 900000+ip;
  const uint32_t observed_crossing = AtOrAfter(crossing, sp);
  const uint32_t begin = uint32_t(int64_t(observed_crossing)+offset), end = begin+100000;
  const bool previously_owned = begin > observed_crossing;
  bench::Controls c; c.Reset(250, false);
  unsigned invalid = 0;
  for (uint32_t us = sp; us < 1200000; us += 1000) {
    uint16_t raw = up ? 0 : 65535;
    if (us >= crossing && us < return_time) raw = up ? 40000 : 5000;
    const bool valid = us < begin || us >= end;
    const auto r = c.Step(us, valid ? raw : 0, valid, false);
    invalid += !valid;
    Check(r.cadence_valid && !r.actions, name, ip, sp, offset, "independent button cadence");
    if (!valid) Check(!r.changed && r.accepted_ppm == -1, name, ip, sp, offset, "invalid samples never apply");
    if (us >= end && us < return_time) {
      Check(r.state == (previously_owned ? 2u : 1u), name, ip, sp, offset, "observed versus missing crossing");
      if (!previously_owned) Check(r.value_ppm == 250000, name, ip, sp, offset, "target held after missing crossing");
    }
    if (us >= return_time) Check(r.state == 2, name, ip, sp, offset, "valid observed return recovers");
  }
  Check(invalid == 100, name, ip, sp, offset, "complete ADC-only injection");
  ++cases;
  if (csv) std::printf("%s,%u,%u,%d,0,0,0,contract\n", name, unsigned(ip), unsigned(sp), offset);
}

static void Cadence(uint32_t ip, uint32_t sp, uint32_t gap) {
  bench::Controls c; c.Reset(250, false);
  unsigned taps = 0, holds = 0, breaks = 0;
  const uint32_t last_before = 200000+sp;
  for (uint32_t us = sp; us < 1600000; us += 1000) {
    // Resume at the exact requested separation, including sub-ms boundaries.
    const uint32_t observed = us > last_before ? us-1000+gap : us;
    const bool pressed = (100000+ip <= observed && observed < 900000+ip) ||
                         (1200000+ip <= observed && observed < 1300000+ip);
    const auto r = c.Step(observed, 0, true, pressed);
    taps += r.gesture == 1; holds += r.gesture == 2; breaks += !r.cadence_valid;
  }
  Check(taps == 1 && holds == (gap <= 10000 ? 1u : 0u) && breaks == (gap > 10000 ? 1u : 0u),
        "cadence_threshold", ip, sp, int(gap), "exact continuity boundary and fresh recovery");
  ++cases;
  if (csv) std::printf("cadence_threshold,%u,%u,%u,%u,%u,%u,contract\n", unsigned(ip), unsigned(sp),
                       unsigned(gap), taps, holds, breaks);
}

int main(int argc, char** argv) {
  if (argc > 2 || (argc == 2 && std::strcmp(argv[1], "--csv"))) {
    std::fprintf(stderr, "Usage: daisy_fault_sweep [--csv]\n"); return 2;
  }
  csv = argc == 2;
  if (csv) std::puts("case,input_phase_us,service_phase_us,fault_offset_us,taps,holds,cadence_breaks,expectation");
  // Sweep event phase within a 1 ms service slot, three fixed service offsets,
  // and both sides of exact qualification/ownership boundaries. Fixed offsets
  // are synthetic scheduling cases, not a substitute for interrupt measurements.
  for (uint32_t ip = 0; ip < 1000; ip += 25) {
    for (uint32_t sp : {0u, 137u, 233u}) {
      for (int offset : {-1001, -1000, -1, 0, 1, 1000, 1001}) {
        Button("press_qualification", 0, ip, sp, offset);
        Button("hold_deadline", 1, ip, sp, offset);
        Button("release_qualification", 2, ip, sp, offset);
        Button("adc_only_release", 3, ip, sp, offset);
        Pickup(true, ip, sp, offset); Pickup(false, ip, sp, offset);
      }
      for (uint32_t gap : {9999u, 10000u, 10001u}) Cadence(ip, sp, gap);
    }
  }
  Check(cases == 5400 && pending_press_cases == 480, "coverage", 0, 0, 0, "campaign completed");
  std::fprintf(csv ? stderr : stdout, "PASS: %u synthetic phase cases; %u explicitly retain pending-press requalification (not cancellation). No hardware qualification.\n",
               unsigned(cases), unsigned(pending_press_cases));
}
