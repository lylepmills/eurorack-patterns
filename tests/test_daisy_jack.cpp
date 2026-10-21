// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "../examples/daisy/jack_bench.h"
#include "../examples/daisy/protocol.h"
#include <cstring>
#include <cstdlib>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)
using namespace jackbench;
static Record Sample(uint32_t i, bool probe, uint16_t raw) {
  Record r{}; r.seq = i; r.slot = i; r.drive_us = i * kPeriodUs;
  r.sample_us = r.drive_us + kSettleUs; r.adc_end_us = r.sample_us + 140;
  r.end_us = r.adc_end_us + 5; r.probe = probe; r.raw = raw; r.adc_valid = 1;
  return r;
}
static void Trace(int mode = 0) {
  const bool finish = mode == 1, motion = mode == 2;
#ifdef _WIN32
  // Emit the firmware's exact LF bytes, including the bytes covered by FNV.
  // CRT text mode would translate them to CRLF after the checksum is computed.
  CHECK(_setmode(_fileno(stdout), _O_BINARY) != -1);
#endif
  std::printf("JINFO,{\"kind\":\"daisy-jack-bench\",\"protocol\":%u,\"board\":\"seed3\",\"build_id\":\"0123456789abcdef01234567\",\"ready\":true,\"period_us\":500,\"settle_us\":150,\"window_size\":64,\"mismatch_threshold\":3,\"bad_windows_required\":8,\"low_code\":16384,\"high_code\":49151,\"max_records\":600000,\"timer_hz\":240000000,\"adc_hz\":6145833,\"sample_cycles_x2\":1621}\n", finish ? 2 : 1);
  std::puts(finish ? "JSTART,7,300000,0,1" : motion ? "JSTART,7,30000,0,1" : "JSTART,7,3000,1,1");
  uint32_t hash = 2166136261u;
  auto emit = [&](const char* s) { std::fputs(s, stdout); hash = bench::Hash(hash, s, std::strlen(s)); };
  if (finish) emit("JFINISH,7,1234199,1234500,1\n");
  emit(finish || motion ? "JFAULT,0,0\n" : "JFAULT,2000150,2025150\n");
  char line[384]; std::snprintf(line, sizeof(line), "JCOLUMNS,%s\n", kColumns); emit(line);
  Detector detector(1); Probe probe;
  const uint32_t count = finish ? 2469 : motion ? 60000 : 6000;
  for (uint32_t i = 0; i < count; ++i) {
    const bool bit = probe.Next();
    const bool empty = motion ? !((i>=4000 && i<12000) || (i>=20000 && i<28000) || (i>=36000 && i<44000)) : (i<800 || i>=4800);
    Record r = Sample(i, bit, empty && bit ? 65535 : 0);
    r.injected = !finish && !motion && i >= 4000 && i < 4050;
    detector.Observe(r, false); Format(line, sizeof(line), r); emit(line);
  }
  std::printf("JEND,7,%u,0,0,0,%u,%u\n", unsigned(count), finish ? 1234500 : motion ? 30000000 : 3000000, unsigned(hash));
}
int main(int argc, char** argv) {
  if (argc == 2 && std::strcmp(argv[1], "--trace") == 0) { Trace(); return 0; }
  if (argc == 2 && std::strcmp(argv[1], "--finish-trace") == 0) { Trace(1); return 0; }
  if (argc == 2 && std::strcmp(argv[1], "--motion-trace") == 0) { Trace(2); return 0; }
  Plan p;
  CHECK(Parse("J,4294967295,300000,2,0", p));
  const char* bad[] = {"", "J", "J,", "J,1", "J,1,1000,0", "J,1,999,0,1",
    "J,1,300001,0,1", "J,1,2000,1,1", "J,1,3000,3,1", "J,1,3000,0,2",
    "J,-1,1000,0,1", "J,4294967296,1000,0,1", "J,1,1000,0,1,", "J,1,1000,0,1x"};
  for (auto s : bad) { CHECK(!Parse(s, p)); CHECK(p.token == UINT32_MAX); }
  FinishCommand finish;
  for (uint32_t token : {0u, 7u, UINT32_MAX}) {
    char text[16]; std::snprintf(text, sizeof(text), "JF,%u\n", unsigned(token));
    finish.Reset(token);
    for (int repeat = 0; repeat < 2; ++repeat) {
      for (size_t i = 0; i < std::strlen(text); ++i)
        CHECK(finish.Feed(text[i]) == (text[i] == '\n' ? FinishCommand::Result::kComplete : FinishCommand::Result::kPartial));
      CHECK(!finish.Incomplete());
    }
  }
  for (const char* text : {"?\n", "JF,8\n", "JF,07\n", "JF,7\r\n", "JF,4294967296\n", "JF,7\nX"}) {
    finish.Reset(7); bool invalid = false;
    for (const char* s = text; *s; ++s) invalid |= finish.Feed(*s) == FinishCommand::Result::kInvalid;
    CHECK(invalid && finish.Incomplete());
    CHECK(finish.Feed('\n') == FinishCommand::Result::kInvalid);
  }
  finish.Reset(7); CHECK(finish.Feed('J') == FinishCommand::Result::kPartial && finish.Incomplete());
  Plan limit; CHECK(Parse("J,7,300000,0,1", limit));
  CHECK(FinishLimit(limit, 1) == 1000000 && FinishLimit(limit, 1234199) == 1234500);
  CHECK(FinishLimit(limit, 1234500) == 1234500 && FinishLimit(limit, 299999999) == 300000000);
  limit.fault = 1; CHECK(FinishLimit(limit, 1234199) == 3000000);
  Probe a, b; uint32_t ones = 0, run = 0, longest = 0; bool last = false;
  bool prefix[32]{};
  for (uint32_t i = 0; i < 65535; ++i) {
    bool bit = a.Next(); CHECK(bit == b.Next()); ones += bit;
    if (i < 32) prefix[i] = bit;
    run = i && bit == last ? run + 1 : 1; if (run > longest) longest = run; last = bit;
  }
  CHECK(ones == 32768 && longest <= 16);
  for (auto bit : prefix) CHECK(a.Next() == bit);
  Schedule schedule;
  CHECK(schedule.Due(0) && schedule.Take(0) == 0);
  CHECK(!schedule.Due(499) && schedule.Due(500));
  CHECK(schedule.Take(2500) == 4 && !schedule.Due(2500));
  Detector detector(1); Record r{};
  for (uint32_t i = 0; i < 64; ++i) { r = Sample(i, i % 2, i % 2 ? 65535 : 0); detector.Observe(r, false); }
  CHECK(r.ready && !r.patched && r.windows == 1);
  // A constant silent input creates 32 mismatches/window, qualifying at eight.
  for (uint32_t i = 64; i < 576; ++i) {
    r = Sample(i, i % 2, 0); detector.Observe(r, false);
    CHECK(bool(r.patched) == (i == 575));
  }
  r = Sample(576, true, 65535); detector.Observe(r, true);
  CHECK(r.evidence == 2 && r.patched && r.bad_windows == 0);
  for (uint32_t i = 577; i < 641; ++i) {
    r = Sample(i, true, 65535); detector.Observe(r, false);
    CHECK(bool(r.patched) == (i < 640));
  }
  // Invalid evidence must never be mistaken for a mismatch or a good window.
  r = Sample(0, false, 32768); CHECK(Evidence(r, false) == eurorack_patterns::PresenceEvidence::kInvalid);
  r.raw = kLow; CHECK(Evidence(r, false) == eurorack_patterns::PresenceEvidence::kMatch);
  r.raw = kHigh; CHECK(Evidence(r, false) == eurorack_patterns::PresenceEvidence::kMismatch);
  r.sample_us = kSettleUs - 1; CHECK(Evidence(r, false) == eurorack_patterns::PresenceEvidence::kInvalid);
  r.sample_us = kSettleUs; r.adc_end_us = kPeriodUs;
  CHECK(Evidence(r, false) == eurorack_patterns::PresenceEvidence::kInvalid);
  r.adc_end_us = 300; r.injected = 1; CHECK(Evidence(r, false) == eurorack_patterns::PresenceEvidence::kInvalid);
  r.injected = 0; r.adc_valid = 0; CHECK(Evidence(r, false) == eurorack_patterns::PresenceEvidence::kInvalid);
  Detector first(0), streak(1);
  for (uint32_t i = 0; i < 64; ++i) {
    r = Sample(i, true, 0); first.Observe(r, false);
    Record s = Sample(i, true, 0); streak.Observe(s, false); CHECK(!s.ready);
  }
  CHECK(r.ready && r.patched);
  // An externally correlated signal is indistinguishable from the normal.
  Detector correlated(1); Probe probe;
  for (uint32_t i = 0; i < 1024; ++i) {
    const bool bit = probe.Next(); r = Sample(i, bit, bit ? 65535 : 0); correlated.Observe(r, false);
  }
  CHECK(r.ready && !r.patched);
  std::puts("PASS: jack adapter freshness, timing gaps, qualification, probe balance, correlated counterexample");
}
