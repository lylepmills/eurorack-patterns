// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "protocol.h"
#include "experiment.h"
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

static bool Numbers(const std::string& text, std::vector<int64_t>& out) {
  out.clear(); std::stringstream stream(text); std::string word;
  while (std::getline(stream, word, ',')) {
    char* end = nullptr; errno = 0;
    const auto n = std::strtoll(word.c_str(), &end, 10);
    if (errno || end == word.c_str() || *end) return false;
    out.push_back(n);
  }
  return true;
}
static bool Close(int32_t a, int64_t b) { return std::llabs(int64_t(a) - b) <= 1; }
static int Replay(const char* path) {
  std::ifstream file(path, std::ios::binary); if (!file) return 1;
  std::string line; bench::Controls controls; bool started = false, ended = false;
  uint32_t count = 0, hash = 2166136261u; int64_t token = -1, scenario = -1;
  bool stimulus_seen = false, timing_seen = false, columns_seen = false;
  std::vector<int64_t> n;
  while (std::getline(file, line)) {
    if (line.compare(0, 6, "START,") == 0) {
      if (started || !Numbers(line.substr(6), n) || n.size() != 5 ||
          n[3] < 0 || n[3] > 1000 || n[4] < 0 || n[4] > 1) return 1;
      controls.Reset(uint32_t(n[3]), n[4] != 0); token = n[0]; scenario = n[1]; started = true;
    } else if (line.compare(0, 9, "STIMULUS,") == 0) {
      if (!started || stimulus_seen || columns_seen || count || ended) return 1;
      stimulus_seen = true;
      line += '\n'; hash = bench::Hash(hash, line.data(), line.size());
    } else if (line.compare(0, 12, "FAULTTIMING,") == 0) {
      if (!started || !stimulus_seen || timing_seen || columns_seen || count || ended ||
          scenario < bench::kPressStall || scenario > bench::kPressAdcGap ||
          !Numbers(line.substr(12), n) || n.size() != 1 || n[0] < 1 || n[0] > 1000000) return 1;
      timing_seen = true;
      line += '\n'; hash = bench::Hash(hash, line.data(), line.size());
    } else if (line.compare(0, 8, "COLUMNS,") == 0) {
      if (!started || columns_seen || count || ended) return 1;
      columns_seen = true;
    } else if (line.compare(0, 2, "D,") == 0) {
      if (!started || !columns_seen || ended || !Numbers(line.substr(2), n) || n.size() != 19 ||
          n[0] != count || n[1] < 0 || n[1] >= bench::kMaxDurationMs * 1000 || n[4] < 0 || n[4] > 65535 ||
          n[8] < -1 || n[8] > 1000) return 1;
      const auto r = controls.Step(uint32_t(n[1]), uint16_t(n[4]), n[5] != 0,
                                   n[7] != 0, int32_t(n[8]));
      if (r.cadence_valid != bool(n[9]) || !Close(r.accepted_ppm, n[10]) ||
          !Close(r.value_ppm, n[11]) || !Close(r.target_ppm, n[12]) ||
          r.state != n[13] || r.debounced != bool(n[14]) || r.gesture != n[15] ||
          r.changed != bool(n[16]) || r.actions != n[17]) {
        std::cerr << "Replay mismatch at sample " << count << '\n'; return 1;
      }
      line += '\n'; hash = bench::Hash(hash, line.data(), line.size()); ++count;
    } else if (line.compare(0, 4, "END,") == 0) {
      if (ended || !Numbers(line.substr(4), n) || n.size() != 8 ||
          n[0] != token || n[1] != count || n[6] != hash) return 1;
      ended = true;
    } else if (line.compare(0, 5, "INFO,") && line.compare(0, 8, "COLUMNS,")) return 1;
  }
  if (!started || !ended || !count) return 1;
  std::cout << "PASS: " << count << " samples replayed through the C++ adapter; not independent hardware validation\n";
  return 0;
}
static int Synthetic(unsigned scenario, bool force_v2 = false, bool long_window = false, uint32_t fault_delay_us = 0) {
  if (scenario > bench::kStartup || (fault_delay_us &&
      (scenario < bench::kPressStall || scenario > bench::kPressAdcGap || fault_delay_us > 1000000))) return 1;
  // Generated stimulus. Pipeline tests only; never physical evidence.
  const bool version2 = force_v2 || long_window || scenario >= bench::kPressStall;
  const bool startup = scenario == bench::kStartup;
  const uint32_t duration = startup ? bench::kStartupDurationMs : long_window ? bench::kMaxDurationMs : 6000;
  std::printf("INFO,{\"protocol\":%u,\"build_id\":\"synthetic\",\"board\":\"seed3\",\"ready\":true,\"period_us\":1000,\"max_records\":%u,\"sample_cycles_x2\":1621,\"oversampling\":1,\"startup_available\":%s,\"fault_timing\":1}\n",
              version2 ? 2u : 1u, long_window ? unsigned(bench::kMaxRecords) : 30000u, startup ? "true" : "false");
  std::printf("START,42,%u,%u,250,%u\n", scenario, duration, unsigned(startup));
  bench::Controls controls; controls.Reset(250, startup);
  bench::Experiment experiment(scenario, startup, fault_delay_us);
  bench::Schedule schedule;
  uint32_t seq = 0, missed = 0;
  std::vector<bench::Record> records;
  for (uint32_t us = 0; us < duration * 1000; us += 1000) {
    if (experiment.Stall(us)) { us += 25000; experiment.EndStall(us); }
    if (us >= duration * 1000) break;
    missed += schedule.Take(us);
    const bool injected = experiment.InvalidAdc(us);
    // The long-window case leaves two full minutes for an operator to begin.
    const uint32_t t = long_window ? (us < 120000000 ? 0 : us - 120000000) : us;
    bool pressed = startup ? t < 800000 || (t >= 1100000 && t < 1200000) :
                                  (t >= 200000 && t < 900000) || (t >= 1100000 && t < 1200000);
    if (scenario >= bench::kPickupGapUp && scenario <= bench::kMovingTarget) pressed = false;
    if (scenario == bench::kReleaseStall || scenario == bench::kPressAdcGap)
      pressed = (t >= 200000 && t < 300000) || (t >= 1100000 && t < 1200000);
    uint16_t raw = uint16_t((t / 1000 * 37) % 65536);
    if (scenario == bench::kPickupGapUp || scenario == bench::kMovingTarget)
      raw = uint16_t(t >= 2000000 ? 65535 : t * 65535ull / 2000000);
    if (scenario == bench::kPickupGapDown)
      raw = uint16_t(t >= 2000000 ? 0 : 65535 - t * 65535ull / 2000000);
    if (injected) raw = 0;
    int32_t external = experiment.Observe(us, raw, !injected, pressed);
    if (scenario == bench::kTargets && us == 5000000) external = 750;
    const auto result = controls.Step(us, raw, !injected, pressed, external);
    bench::Record r{seq++, us, injected ? 0u : 35u, scenario == bench::kLoad ? 440u : 40u,
                    raw, !injected, injected, pressed, external, result, missed};
    records.push_back(r);
  }
  char line[512]; uint32_t hash = 2166136261u;
  if (version2) {
    const auto& s = experiment.stimulus();
    const int size = std::snprintf(line, sizeof(line), "STIMULUS,%d,%d,%d\n", int(s.trigger), int(s.begin), int(s.end));
    hash = bench::Hash(hash, line, size_t(size)); std::fputs(line, stdout);
  }
  if (fault_delay_us) {
    const int size = std::snprintf(line, sizeof(line), "FAULTTIMING,%u\n", unsigned(fault_delay_us));
    hash = bench::Hash(hash, line, size_t(size)); std::fputs(line, stdout);
  }
  std::printf("COLUMNS,%s\n", bench::kColumns);
  for (const auto& r : records) {
    const int size = bench::FormatRecord(line, sizeof(line), r);
    hash = bench::Hash(hash, line, size_t(size)); std::fputs(line, stdout);
  }
  std::printf("END,42,%u,%u,0,0,0,%u,%u\n", seq, missed, hash, duration * 1000);
  return 0;
}

int main(int argc, char** argv) {
  if (argc == 4 && std::strcmp(argv[1], "--synthetic-timed") == 0) {
#ifdef _WIN32
    if (_setmode(_fileno(stdout), _O_BINARY) == -1) return 1;
#endif
    std::vector<int64_t> delay;
    if (!Numbers(argv[3], delay) || delay.size() != 1 || delay[0] < 1 || delay[0] > 1000000) return 1;
    return Synthetic(unsigned(std::atoi(argv[2])), true, false, uint32_t(delay[0]));
  }
  if (argc == 3 && (std::strcmp(argv[1], "--synthetic") == 0 || std::strcmp(argv[1], "--synthetic-v2") == 0 ||
                    std::strcmp(argv[1], "--synthetic-long") == 0)) {
#ifdef _WIN32
    // Protocol checksums cover exact wire bytes, including LF line endings.
    if (_setmode(_fileno(stdout), _O_BINARY) == -1) return 1;
#endif
    return Synthetic(unsigned(std::atoi(argv[2])), std::strcmp(argv[1], "--synthetic-v2") == 0,
                     std::strcmp(argv[1], "--synthetic-long") == 0);
  }
  if (argc == 2) return Replay(argv[1]);
  std::cerr << "Usage: daisy_replay raw.txt | --synthetic SCENARIO_ID\n";
  return 1;
}
