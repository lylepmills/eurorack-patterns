// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "../examples/daisy/dsp_workload.h"
#include "../examples/daisy/jack_bench.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)
static dspbench::Signature Render(uint32_t voices, uint32_t frames) {
  std::vector<int16_t> memory(voices * dspbench::kDelay);
  dspbench::Engine engine; engine.Reset(voices, memory.data());
  for (uint32_t i = 0; i < frames; ++i) { int16_t l, r; engine.Frame(l, r); }
  return engine.signature();
}
int main(int argc, char** argv) {
  if (argc == 4 && std::strcmp(argv[1], "--signature") == 0) {
    const uint32_t voices = uint32_t(std::strtoul(argv[2], nullptr, 10));
    const uint32_t frames = uint32_t(std::strtoul(argv[3], nullptr, 10));
    CHECK(voices > 0 && voices <= 32 && frames <= 1440000);
    const auto r = Render(voices, frames);
    std::printf("{\"frames\":%u,\"hash\":%u,\"peak\":%u,\"nonzero\":%u,\"macs\":%u}\n",
        unsigned(r.frames),unsigned(r.hash),unsigned(r.peak),unsigned(r.nonzero),unsigned(r.macs));
    return 0;
  }
  // Analytic impulse and DC checks, including negative truncation, exercise
  // the actual FIR rather than comparing it only against another copy.
  for (int32_t sign : {-1, 1}) {
    dspbench::Fir filter;
    for (uint32_t i = 0; i < 64; ++i) {
      const int32_t coefficient = i < 16 ? int32_t(i+1) : i < 32 ? int32_t(32-i) : 0;
      CHECK(filter.Process(int16_t(i == 0 ? sign * 272 : 0)) == sign * coefficient);
    }
    for (unsigned i = 0; i < 64; ++i) {
      const int32_t y = filter.Process(int16_t(sign * 8191));
      if (i >= 31) CHECK(y == sign * 8191);
    }
  }
  for (uint32_t voices : {1u,4u,16u,32u}) {
    const auto a = Render(voices, 70000), b = Render(voices, 70000);
    CHECK(a.hash == b.hash && a.hash != dspbench::kInitialHash);
    CHECK(a.frames == 70000 && a.macs == 70000 * voices * 32);
    CHECK(a.peak > 0 && a.peak <= 10923 && a.nonzero > 69000);
  }
  jackbench::Plan plan;
  CHECK(jackbench::Parse("J,1,10000,0,1,0,0,25000,48,0,8000,16,16", plan));
  CHECK(plan.dsp_voices == 16 && plan.dma_kib == 16);
  for (const char* bad : {"J,1,10000,0,1,0,0,25000,0,0,0,16,0",
      "J,1,10000,0,1,0,0,25000,48,250,8000,16,0",
      "J,1,10000,0,1,0,0,25000,48,0,8000,33,0",
      "J,1,10000,0,1,0,0,25000,48,0,8000,16,8",
      "J,1,31000,0,1,0,0,25000,48,0,8000,16,16",
      "J,1,10000,0,1,0,0,25000,48,0,8000,16"}) CHECK(!jackbench::Parse(bad, plan));
  for (uint32_t epoch = 1; epoch < 100; ++epoch)
    for (uint32_t i = 0; i < 4096; ++i) CHECK(dspbench::Word(epoch,i) != dspbench::Word(epoch-1,i));
  std::puts("PASS deterministic FIR/delay workload, reset, wrap and bounds");
}
