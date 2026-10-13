// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "eurorack_patterns/events.h"

#include <cstdio>
#include <cstdlib>
#include <limits>
#include <sstream>
#include <string>

#include "traces/events_thresholds.h"
#include "traces/events_saturation.h"

using namespace eurorack_patterns;

#define CHECK(condition) do { if (!(condition)) { \
  std::fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
  std::exit(1); } } while (0)

static void Replay(const char* name, const char* trace) {
  RisingEdgeCapture<int> edges;
  std::istringstream input(trace);
  std::string line;
  unsigned line_number = 0;
  while (std::getline(input, line)) {
    ++line_number;
    if (line.empty() || line[0] == '#') continue;
    std::istringstream fields(line);
    std::string command;
    fields >> command;
    if (command == "config") {
      int low = 0, high = 0;
      unsigned capacity = 0;
      std::string policy;
      CHECK(bool(fields >> low >> high >> capacity >> policy));
      CHECK(policy == "silent" || policy == "count");
      CHECK(edges.Configure(low, high, static_cast<uint16_t>(capacity),
          policy == "silent" ? HighAcquisitionPolicy::kSeedSilently
                             : HighAcquisitionPolicy::kCountAsRise));
    } else if (command == "sample") {
      int value = 0;
      unsigned repeat = 0;
      CHECK(bool(fields >> value >> repeat));
      for (unsigned i = 0; i < repeat; ++i) edges.Observe(value);
    } else if (command == "invalid") {
      unsigned repeat = 0;
      CHECK(bool(fields >> repeat));
      for (unsigned i = 0; i < repeat; ++i) edges.Observe(0, false);
    } else if (command == "consume") {
      unsigned maximum = 0, expected = 0;
      CHECK(bool(fields >> maximum >> expected));
      CHECK(edges.Consume(static_cast<uint16_t>(maximum)) == expected);
    } else if (command == "clear_overflow") {
      edges.ClearOverflow();
    } else if (command == "reset") {
      edges.Reset();
    } else if (command == "expect") {
      unsigned pending = 0, overflow = 0, known = 0, high = 0;
      CHECK(bool(fields >> pending >> overflow >> known >> high));
      if (edges.pending() != pending || edges.overflowed() != (overflow != 0) ||
          edges.level_known() != (known != 0) || edges.high() != (high != 0)) {
        std::fprintf(stderr, "%s:%u: event state mismatch\n", name, line_number);
        std::exit(1);
      }
    } else {
      std::fprintf(stderr, "%s:%u: unknown trace command\n", name, line_number);
      std::exit(1);
    }
  }
}

int main() {
  Replay("thresholds", kEventsThresholdsTrace);
  Replay("saturation", kEventsSaturationTrace);

  RisingEdgeCapture<float> edges;
  const float nan = std::numeric_limits<float>::quiet_NaN();
  const float infinity = std::numeric_limits<float>::infinity();
  CHECK(!edges.configured());
  CHECK(!edges.Observe(5.0f));
  CHECK(!edges.Configure(nan, 3.0f, 2, HighAcquisitionPolicy::kSeedSilently));
  CHECK(!edges.Configure(1.0f, infinity, 2, HighAcquisitionPolicy::kSeedSilently));
  CHECK(!edges.Configure(-infinity, 3.0f, 2, HighAcquisitionPolicy::kSeedSilently));
  CHECK(!edges.Configure(3.0f, 1.0f, 2, HighAcquisitionPolicy::kSeedSilently));
  CHECK(!edges.Configure(1.0f, 3.0f, 0, HighAcquisitionPolicy::kSeedSilently));
  CHECK(edges.Configure(1.0f, 3.0f, 1, HighAcquisitionPolicy::kSeedSilently));
  CHECK(edges.Consume(0) == 0);
  CHECK(!edges.Observe(4.0f));  // Startup high seeds silently.
  CHECK(edges.level_known() && edges.high() && edges.pending() == 0);
  edges.Observe(0.0f);
  CHECK(edges.Observe(4.0f));
  CHECK(!edges.Observe(4.0f));
  CHECK(edges.pending() == 1 && !edges.overflowed());
  CHECK(!edges.Observe(nan));
  CHECK(!edges.level_known() && edges.pending() == 1);
  CHECK(!edges.Observe(infinity));
  CHECK(!edges.level_known() && edges.pending() == 1);
  CHECK(!edges.Observe(-infinity));
  CHECK(!edges.level_known() && edges.pending() == 1);
  CHECK(!edges.Observe(4.0f));  // Reacquired high seeds without another rise.
  CHECK(edges.level_known() && edges.high() && edges.pending() == 1);
  edges.Reset();
  CHECK(edges.configured() && edges.pending() == 0 && !edges.level_known());
  std::puts("event traces passed");
}
