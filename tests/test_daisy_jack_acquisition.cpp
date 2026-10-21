// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "../examples/daisy/jack_acquisition.h"
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
using Action = Acquisition::Action;

static void Simulate(const Plan& p, bool trace) {
  Acquisition a(p);
  std::vector<Record> rows;
  uint32_t pending = 0, timer_irqs = 0, us = 50;
  const uint32_t limit = p.duration_ms * 1000;
  for (; us <= limit + 1000; ++us) {
    if (pending == us) {
      pending = 0;
      const bool empty = us < 3000000 || us >= 6500000;
      a.Converted(empty && a.record.probe ? 65535 : 0, true, us);
      a.Finished(us + 2); rows.push_back(a.record);
    }
    if (us % 50) continue;
    ++timer_irqs;
    const auto action = a.Next(us, limit);
    CHECK(action != Action::kTimeout);
    if (action == Action::kSample) { CHECK(!pending); pending = us + 134; }
    if (action == Action::kFinished) break;
  }
  CHECK(!pending && a.count == rows.size() && !a.failures);
  CHECK(a.missed == (p.fault == 2 ? p.fault_us/500 : 0));
  CHECK(a.count + a.missed == limit/500);
  unsigned injected = 0, invalid = 0, insertions = 0, removals = 0;
  bool patched = false;
  for (const auto& r : rows) {
    injected += r.injected; invalid += r.evidence == 2;
    if (bool(r.patched) != patched) { if (r.patched) ++insertions; else ++removals; patched = r.patched != 0; }
    CHECK(r.sample_us >= r.drive_us + 150 && r.adc_end_us < (r.slot+1)*500);
  }
  CHECK(insertions == 1 && removals == 1);
  CHECK(injected == (p.fault == 1 ? p.fault_us/500 : 0));
  CHECK(invalid == (p.fault == 1 ? injected : p.fault == 2 ? 1u : 0u));
  if (!trace) return;
#ifdef _WIN32
  CHECK(_setmode(_fileno(stdout), _O_BINARY) != -1);
#endif
  std::puts("JINFO,{\"kind\":\"daisy-jack-bench\",\"protocol\":5,\"board\":\"seed3\",\"build_id\":\"0123456789abcdef01234567\",\"ready\":true,\"period_us\":500,\"settle_us\":150,\"window_size\":64,\"mismatch_threshold\":3,\"bad_windows_required\":8,\"low_code\":16384,\"high_code\":49151,\"max_records\":600000,\"timer_hz\":240000000,\"adc_hz\":6145833,\"sample_cycles_x2\":1621}");
  std::printf("JSTART,17,10000,%u,1,%u,%u,%u,48,250,8000\n", unsigned(p.fault), unsigned(p.trigger), unsigned(p.delay_slots), unsigned(p.fault_us));
  uint32_t hash = 2166136261u;
  auto emit = [&](const char* text) { std::fputs(text, stdout); hash = bench::Hash(hash, text, std::strlen(text)); };
  char line[384]; emit("JFINISH,17,0,10000000,0\n");
  const auto& f = a.fault();
  std::snprintf(line, sizeof(line), "JTIMING,%u,%u,%u,%u,%u,%u\n", unsigned(p.trigger), unsigned(p.delay_slots), unsigned(p.fault_us), unsigned(f.event_seq()), unsigned(f.event_us()), unsigned(f.due_us())); emit(line);
  emit("JLOAD,48,250,8000,8000000,8000,61000,240000,0,0,0,240000,240000000\n");
  std::snprintf(line, sizeof(line), "JACQ,50,0,0,1,%u,%u,240,480,57600000,0,0,0,0,1\n", unsigned(timer_irqs), unsigned(a.count)); emit(line);
  std::snprintf(line, sizeof(line), "JFAULT,%u,%u\n", unsigned(a.fault_begin), unsigned(a.fault_end)); emit(line);
  std::snprintf(line, sizeof(line), "JCOLUMNS,%s\n", kColumns); emit(line);
  for (const auto& r : rows) { Format(line, sizeof(line), r); emit(line); }
  std::printf("JEND,17,%u,0,%u,0,%u,%u\n", unsigned(a.count), unsigned(a.missed), unsigned(us), unsigned(hash));
}

int main(int argc, char** argv) {
  Plan p; p.token = 17; p.duration_ms = 10000;
  if (argc == 4 && std::strcmp(argv[1], "--trace") == 0) {
    p.fault = static_cast<uint32_t>(std::strtoul(argv[2], nullptr, 10));
    p.trigger = static_cast<uint32_t>(std::strtoul(argv[3], nullptr, 10));
    CHECK(p.Valid()); Simulate(p, true); return 0;
  }
  Simulate(p, false);
  for (uint32_t fault : {1u, 2u}) for (uint32_t trigger = 0; trigger <= 6; ++trigger)
    for (uint32_t duration : {500u, 25000u, 100000u}) for (uint32_t delay : {0u, 1u, 64u}) {
      if (!trigger && delay) continue;
      p.fault = fault; p.trigger = trigger; p.fault_us = duration; p.delay_slots = delay;
      CHECK(p.Valid()); Simulate(p, false);
    }
  p.fault = 0; p.trigger = 0; p.delay_slots = 0; p.fault_us = 25000;
  CHECK(ScheduledFinishLimit(p, 0) == 1000000);
  CHECK(ScheduledFinishLimit(p, 1234499) == 1234500);
  CHECK(ScheduledFinishLimit(p, 1234500) == 1235000);
  CHECK(ScheduledFinishLimit(p, 9999999) == 10000000);
  for (uint32_t request = 1234490; request <= 1235010; ++request) {
    const uint32_t boundary = ScheduledFinishLimit(p, request);
    CHECK(request < boundary && boundary - request <= 500);
    CHECK((request / 500) < boundary / 500);
  }
  Acquisition delayed(p);
  CHECK(delayed.Next(50,10000) == Action::kDrive);
  CHECK(delayed.Next(199,10000) == Action::kNone);
  CHECK(delayed.Next(200,10000) == Action::kSample);
  CHECK(delayed.Next(699,10000) == Action::kNone);
  CHECK(delayed.Next(700,10000) == Action::kTimeout);
  delayed.Converted(0,false,700); delayed.Finished(702);
  CHECK(delayed.record.evidence == 2 && delayed.failures == 1);
  CHECK(delayed.Next(3500,10000) == Action::kDrive);
  CHECK(delayed.missed == 6 && delayed.count == 1);
  CHECK(delayed.Next(3650,3600) == Action::kSample); // Finish the in-flight slot.
  delayed.Converted(delayed.record.probe ? 65535 : 0,true,3784); delayed.Finished(3786);
  CHECK(delayed.record.evidence == 2); // Gap cannot become evidence.
  CHECK(delayed.Next(3800,3600) == Action::kFinished);
  std::puts("PASS: asynchronous phases, 114 fault schedules, timeout, no catch-up, finish drain");
}
