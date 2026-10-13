// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "eurorack_patterns/presence.h"

#include <cstdio>
#include <cstdlib>
#include <sstream>
#include <string>

#include "traces/presence_startup.h"
#include "traces/presence_chatter.h"
#include "traces/presence_sequence_gaps.h"

using namespace eurorack_patterns;

#define CHECK(condition) do { if (!(condition)) { \
  std::fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
  std::exit(1); } } while (0)

static void Replay(const char* name, const char* trace) {
  PresenceDetector detector;
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
      unsigned window = 0, threshold = 0, streak = 0, patched = 0;
      std::string policy, known;
      CHECK(bool(fields >> window >> threshold >> streak >> policy >> known >> patched));
      const PresenceConfig config = {
          static_cast<uint16_t>(window), static_cast<uint16_t>(threshold),
          static_cast<uint16_t>(streak),
          policy == "first" ? PresenceStartupPolicy::kFirstWindowDecides
                            : PresenceStartupPolicy::kRequireStreak};
      CHECK(policy == "first" || policy == "streak");
      CHECK(known == "known" || known == "unknown");
      CHECK(detector.Configure(config, {known == "known", patched != 0}));
    } else if (command == "expect") {
      unsigned ready = 0, patched = 0, windows = 0, bad = 0, partial = 0;
      CHECK(bool(fields >> ready >> patched >> windows >> bad >> partial));
      if (detector.ready() != (ready != 0) ||
          detector.patched() != (patched != 0) ||
          detector.windows() != windows || detector.bad_windows() != bad ||
          detector.observations() != partial) {
        std::fprintf(stderr, "%s:%u: presence state mismatch\n", name, line_number);
        std::exit(1);
      }
    } else {
      unsigned count = 0;
      CHECK(bool(fields >> count));
      CHECK(command == "match" || command == "mismatch" ||
            command == "invalid" || command == "missing" ||
            command == "duplicate");
      const PresenceEvidence evidence =
          command == "match" ? PresenceEvidence::kMatch :
          command == "mismatch" ? PresenceEvidence::kMismatch :
          PresenceEvidence::kInvalid;
      for (unsigned i = 0; i < count; ++i) detector.Observe(evidence);
    }
  }
}

int main() {
  Replay("startup", kPresenceStartupTrace);
  Replay("chatter", kPresenceChatterTrace);
  Replay("sequence gaps", kPresenceSequenceGapsTrace);

  PresenceDetector d;
  CHECK(!d.configured());
  CHECK(!d.Observe(PresenceEvidence::kMismatch));
  CHECK(!d.Configure({0, 1, 2, PresenceStartupPolicy::kFirstWindowDecides}, {false, false}));
  CHECK(!d.Configure({4, 0, 2, PresenceStartupPolicy::kFirstWindowDecides}, {false, false}));
  CHECK(!d.Configure({4, 5, 2, PresenceStartupPolicy::kFirstWindowDecides}, {false, false}));
  CHECK(!d.Configure({4, 2, 0, PresenceStartupPolicy::kFirstWindowDecides}, {false, false}));
  CHECK(d.Configure({4, 2, 3, PresenceStartupPolicy::kRequireStreak}, {true, true}));
  CHECK(d.ready() && d.patched());
  d.Observe(PresenceEvidence::kMismatch);
  CHECK(d.observations() == 1 && d.mismatches() == 1);
  d.Observe(PresenceEvidence::kInvalid);
  CHECK(d.ready() && d.patched() && d.observations() == 0 && d.mismatches() == 0);
  for (int i = 0; i < 4; ++i) d.Observe(PresenceEvidence::kMismatch);
  CHECK(d.ready() && d.patched() && d.bad_windows() == 1 && d.last_mismatches() == 4);
  for (int i = 0; i < 4; ++i) d.Observe(PresenceEvidence::kMatch);
  CHECK(d.ready() && !d.patched() && d.bad_windows() == 0 && d.last_mismatches() == 0);
  std::puts("presence traces passed");
}
