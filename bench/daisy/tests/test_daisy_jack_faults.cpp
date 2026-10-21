// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "../examples/daisy/jack_bench.h"
#include "../examples/daisy/protocol.h"
#include <cstdlib>
#include <cstring>
#include <vector>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)
using namespace jackbench;

static void Trace(const Plan& plan, unsigned scenario) {
#ifdef _WIN32
  CHECK(_setmode(_fileno(stdout), _O_BINARY) != -1);
#endif
  Detector detector(plan.policy); FaultTiming fault(plan); Probe probe; Schedule schedule;
  std::vector<Record> rows;
  uint32_t missed = 0, begin = 0, end = 0;
  for (uint32_t us = 0; us < plan.duration_ms * 1000;) {
    if (!begin && fault.PauseDue(us)) { begin = us; us += plan.fault_us; end = us; continue; }
    Record r{}; r.seq = static_cast<uint32_t>(rows.size()); r.slot = us / kPeriodUs;
    r.drive_us = us; r.sample_us = us + kSettleUs; r.adc_end_us = us + 290; r.end_us = us + 295;
    if (plan.audio_block && plan.audio_permille == 700 && us < plan.audio_off_ms * 1000) {
      // Synthetic preemption repeatedly crosses the slot boundary. Actual
      // workload percentages are measured on hardware, not inferred here.
      r.adc_end_us = us + 600; r.end_us = us + 605;
    }
    const uint32_t skipped = schedule.Take(us); missed += skipped; r.missed = missed;
    r.probe = probe.Next(); r.adc_valid = 1;
    // Scenario 1 never inserts; 2 starts inserted and never establishes empty.
    const bool empty = scenario == 1 || (scenario == 0 && (us < 3000000 || us >= 6500000));
    r.raw = empty && r.probe ? 65535 : 0;
    r.injected = fault.Inject(r.sample_us);
    if (r.injected && !begin) begin = r.sample_us;
    if (plan.fault == 1 && begin && !r.injected && !end) end = r.sample_us;
    detector.Observe(r, skipped != 0);
    rows.push_back(r); fault.Observe(r, detector);
    us = (r.end_us / kPeriodUs + 1) * kPeriodUs;
  }
  std::printf("JINFO,{\"kind\":\"daisy-jack-bench\",\"protocol\":%u,\"board\":\"seed3\",\"build_id\":\"0123456789abcdef01234567\",\"ready\":true,\"period_us\":500,\"settle_us\":150,\"window_size\":64,\"mismatch_threshold\":3,\"bad_windows_required\":8,\"low_code\":16384,\"high_code\":49151,\"max_records\":600000,\"timer_hz\":240000000,\"adc_hz\":6145833,\"sample_cycles_x2\":1621}\n", plan.audio_block ? 4u : 3u);
  std::printf("JSTART,%u,%u,%u,%u,%u,%u,%u", unsigned(plan.token), unsigned(plan.duration_ms),
    unsigned(plan.fault), unsigned(plan.policy), unsigned(plan.trigger), unsigned(plan.delay_slots), unsigned(plan.fault_us));
  if (plan.audio_block) std::printf(",%u,%u,%u", unsigned(plan.audio_block), unsigned(plan.audio_permille), unsigned(plan.audio_off_ms));
  std::printf("\n");
  uint32_t hash = 2166136261u;
  auto emit = [&](const char* text) { std::fputs(text, stdout); hash = bench::Hash(hash, text, std::strlen(text)); };
  char line[384];
  std::snprintf(line, sizeof(line), "JFINISH,%u,0,%u,0\n", unsigned(plan.token), unsigned(plan.duration_ms * 1000)); emit(line);
  std::snprintf(line, sizeof(line), "JTIMING,%u,%u,%u,%u,%u,%u\n", unsigned(plan.trigger),
    unsigned(plan.delay_slots), unsigned(plan.fault_us), unsigned(fault.event_seq()), unsigned(fault.event_us()), unsigned(fault.due_us())); emit(line);
  if (plan.audio_block) {
    const uint32_t period = 240000000u / 48000 * plan.audio_block;
    std::snprintf(line, sizeof(line), "JLOAD,%u,%u,%u,%u,%u,%u,%u,0,0,0,%u,240000000\n",
      unsigned(plan.audio_block), unsigned(plan.audio_permille), unsigned(plan.audio_off_ms),
      unsigned(plan.audio_off_ms*1000), unsigned(plan.audio_off_ms*48/plan.audio_block),
      unsigned(period*plan.audio_permille/1000+240), unsigned(period), unsigned(period)); emit(line);
  }
  std::snprintf(line, sizeof(line), "JFAULT,%u,%u\n", unsigned(begin), unsigned(end)); emit(line);
  std::snprintf(line, sizeof(line), "JCOLUMNS,%s\n", kColumns); emit(line);
  for (const auto& r : rows) { Format(line, sizeof(line), r); emit(line); }
  std::printf("JEND,%u,%u,0,%u,0,%u,%u\n", unsigned(plan.token), unsigned(rows.size()),
    unsigned(missed), unsigned(plan.duration_ms * 1000), unsigned(hash));
}

int main(int argc, char** argv) {
  if (argc == 7 && std::strcmp(argv[1], "--trace") == 0) {
    Plan p; p.token = 17; p.duration_ms = 10000;
    p.fault = static_cast<uint32_t>(std::strtoul(argv[2], nullptr, 10));
    p.trigger = static_cast<uint32_t>(std::strtoul(argv[3], nullptr, 10));
    p.delay_slots = static_cast<uint32_t>(std::strtoul(argv[4], nullptr, 10));
    p.fault_us = static_cast<uint32_t>(std::strtoul(argv[5], nullptr, 10));
    CHECK(p.Valid()); Trace(p, static_cast<unsigned>(std::strtoul(argv[6], nullptr, 10))); return 0;
  }
  if (argc == 3 && std::strcmp(argv[1], "--load-trace") == 0) {
    Plan p; p.token = 17; p.duration_ms = 10000; p.audio_block = 48;
    p.audio_permille = static_cast<uint32_t>(std::strtoul(argv[2], nullptr, 10));
    p.audio_off_ms = 8000; CHECK(p.Valid()); Trace(p, 0); return 0;
  }
  Plan p;
  p.duration_ms = 3000; p.audio_block = 16; p.audio_off_ms = 2000;
  p.dsp_voices = 4; p.dma_kib = 4;
  CHECK(ValidClockDiagnosticPlan(p));
  CHECK(ValidClockReferencePlan(p));
  p.duration_ms = 10001; CHECK(!ValidClockDiagnosticPlan(p));
  CHECK(!ValidClockReferencePlan(p));
  p.duration_ms = 3000; p.fault = 1; CHECK(!ValidClockDiagnosticPlan(p));
  CHECK(ValidClockReferencePlan(p));
  p.fault = 2; p.trigger = 5; CHECK(ValidClockReferencePlan(p));
  p.trigger = 0;
  p.fault = 0; p.dsp_voices = p.dma_kib = 0; p.audio_permille = 1;
  CHECK(!ValidClockDiagnosticPlan(p));
  CHECK(!ValidClockReferencePlan(p));
  p = Plan(); CHECK(!ValidClockDiagnosticPlan(p));
  CHECK(Parse("J,17,300000,1,1,2,0,25000", p));
  CHECK(p.trigger == 2 && p.delay_slots == 0 && p.fault_us == 25000);
  CHECK(Parse("J,17,300000,2,1,6,64,100000", p));
  for (const char* bad : {"J,17,3000,1,1,7,0,25000", "J,17,3000,0,1,1,0,25000",
      "J,17,3000,1,0,1,0,25000", "J,17,3000,1,1,0,1,25000", "J,17,3000,1,1,1,65,25000",
      "J,17,3000,1,1,1,0,499", "J,17,3000,1,1,1,0,501", "J,17,3000,1,1,1,0,100500",
      "J,17,3000,1,1,1,0", "J,17,3000,1,1,1,0,500,", "J,17,3000,1,1,1,-1,500"}) {
    CHECK(!Parse(bad, p)); CHECK(p.trigger == 6 && p.fault_us == 100000);
  }
  CHECK(Parse("J,17,3000,1,1", p)); CHECK(p.trigger == 0 && p.fault_us == 25000);
  FaultTiming timed(p); CHECK(!timed.Inject(1999999) && timed.Inject(2000000));
  CHECK(timed.Inject(2024999) && !timed.Inject(2025000));
  // Event conditions require a known empty baseline, and cannot be armed by
  // startup's unknown-to-patched qualification or by stale/invalid evidence.
  for (uint32_t trigger = 1; trigger <= 6; ++trigger) {
    p.trigger = trigger; FaultTiming f(p); Detector detector(1);
    for (uint32_t i = 0; i < 1024; ++i) {
      Record r{}; r.seq = r.slot = i; r.drive_us = i*500; r.sample_us = r.drive_us+150;
      r.adc_end_us = r.drive_us+290; r.end_us = r.drive_us+295;
      r.adc_valid = 1; r.probe = i % 2; r.raw = 0;
      detector.Observe(r, false); f.Observe(r, detector);
    }
    CHECK(f.event_seq() == UINT32_MAX && f.due_us() == 0);
  }
  CHECK(Parse("J,17,10000,0,1,0,0,25000,16,700,8000", p));
  CHECK(p.audio_block == 16 && p.audio_permille == 700 && p.audio_off_ms == 8000);
  for (const char* bad : {"J,17,10000,0,1,0,0,25000,17,0,8000",
      "J,17,10000,0,1,0,0,25000,0,100,0", "J,17,10000,0,1,0,0,25000,48,701,8000",
      "J,17,10000,0,1,0,0,25000,48,100,9500", "J,17,10000,0,1,0,0,25000,48,100",
      "J,17,10000,0,1,0,0,25000,48,100,8000,1",
      "J,17,10000,0,1,0,0,25000,48,100,4294967295"}) CHECK(!Parse(bad,p));
  std::puts("PASS: bounded jack fault plans, legacy defaults, unknown-start exclusion");
}
