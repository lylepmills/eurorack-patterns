// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "protocol.h"
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

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
  std::ifstream file(path); if (!file) return 1;
  std::string line; bench::Controls controls; bool started = false, ended = false;
  uint32_t count = 0, hash = 2166136261u; int64_t token = -1;
  std::vector<int64_t> n;
  while (std::getline(file, line)) {
    if (line.compare(0, 6, "START,") == 0) {
      if (started || !Numbers(line.substr(6), n) || n.size() != 5 ||
          n[3] < 0 || n[3] > 1000 || n[4] < 0 || n[4] > 1) return 1;
      controls.Reset(uint32_t(n[3]), n[4] != 0); token = n[0]; started = true;
    } else if (line.compare(0, 2, "D,") == 0) {
      if (!started || ended || !Numbers(line.substr(2), n) || n.size() != 19 ||
          n[0] != count || n[1] < 0 || n[1] > 30000000 || n[4] < 0 || n[4] > 65535 ||
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
static int Synthetic(unsigned scenario) {
  if (scenario > 4) return 1;
  // Generated stimulus, explicitly identified. Used only to exercise the host
  // capture/replay pipeline; never evidence of physical behavior.
  std::puts("INFO,{\"protocol\":1,\"build_id\":\"synthetic\",\"board\":\"seed3\",\"ready\":true,\"period_us\":1000,\"max_records\":30000,\"sample_cycles_x2\":1621,\"oversampling\":1}");
  std::printf("START,42,%u,6000,250,0\nCOLUMNS,%s\n", scenario, bench::kColumns);
  bench::Controls controls; controls.Reset(250, false);
  uint32_t seq = 0, missed = 0, hash = 2166136261u;
  for (uint32_t us = 0; us < 6000000; us += 1000) {
    if (scenario == 3 && us == 5000000) { us += 25000; missed += 25; }
    const bool injected = scenario == 2 && us >= 5000000 && us < 5250000;
    const bool pressed = (us >= 200000 && us < 900000) || (us >= 1100000 && us < 1200000);
    const uint16_t raw = injected ? 0 : uint16_t((us / 1000 * 37) % 65536);
    const int32_t external = scenario == 1 && us == 5000000 ? 750 : -1;
    const auto result = controls.Step(us, raw, !injected, pressed, external);
    bench::Record r{seq++, us, injected ? 0u : 35u, scenario == 4 ? 440u : 40u,
                    raw, !injected, injected, pressed, external, result, missed};
    char line[512]; const int size = bench::FormatRecord(line, sizeof(line), r);
    hash = bench::Hash(hash, line, size_t(size)); std::fputs(line, stdout);
  }
  std::printf("END,42,%u,%u,0,0,0,%u,6000000\n", seq, missed, hash);
  return 0;
}
int main(int argc, char** argv) {
  if (argc == 3 && std::strcmp(argv[1], "--synthetic") == 0) return Synthetic(unsigned(std::atoi(argv[2])));
  if (argc == 2) return Replay(argv[1]);
  std::cerr << "Usage: daisy_replay raw.txt | --synthetic SCENARIO_ID\n";
  return 1;
}
