// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
// Synthetic contract checks, independent of any physical acquisition system.
#include <eurorack_patterns/controls.h>
#include <eurorack_patterns/events.h>
#include <eurorack_patterns/presence.h>
#include <eurorack_patterns/timing.h>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <initializer_list>
#include <limits>

#define CHECK(x) do { if (!(x)) { \
  std::fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); \
  std::exit(1); } } while (0)
using namespace eurorack_patterns;

static uint32_t Next(uint32_t& state) {
  state = state * 1664525u + 1013904223u;
  return state;
}

static void PresenceWindows() {
  // Exhaust every eight-symbol trace. A prefix before invalid evidence must
  // have no influence on the unfinished window or the next bad-window streak.
  // Compare against a second detector restarted from the published state at
  // each gap. RequireStreak removes the separate first-window startup policy.
  for (unsigned width = 1; width <= 4; ++width) {
    for (unsigned threshold = 1; threshold <= width; ++threshold) {
      for (unsigned streak = 1; streak <= 3; ++streak) {
        const PresenceConfig config = {static_cast<uint16_t>(width),
            static_cast<uint16_t>(threshold), static_cast<uint16_t>(streak),
            PresenceStartupPolicy::kRequireStreak};
        for (unsigned trace = 0; trace < 6561; ++trace) {
          PresenceDetector a, b;
          CHECK(a.Configure(config, {false, false}));
          CHECK(b.Configure(config, {false, false}));
          unsigned symbols = trace;
          for (unsigned i = 0; i < 8; ++i, symbols /= 3) {
            const unsigned symbol = symbols % 3;
            if (symbol == 2) {
              const bool ready = a.ready(), patched = a.patched();
              CHECK(!a.Observe(PresenceEvidence::kInvalid));
              CHECK(a.ready() == ready && a.patched() == patched);
              CHECK(b.Configure(config, {ready, patched}));
            } else {
              const PresenceEvidence input = symbol == 0
                  ? PresenceEvidence::kMatch : PresenceEvidence::kMismatch;
              CHECK(a.Observe(input) == b.Observe(input));
            }
            CHECK(a.ready() == b.ready() && a.patched() == b.patched());
            CHECK(a.observations() == b.observations());
            CHECK(a.mismatches() == b.mismatches());
            CHECK(a.bad_windows() == b.bad_windows());
            CHECK(a.observations() < width && a.mismatches() <= a.observations());
            CHECK(a.bad_windows() <= streak);
          }
        }
      }
    }
  }
}

// A three-state reference for the fixed 0/1 thresholds below. It has no
// RisingEdgeCapture instance or queue, so a shared acquisition mistake cannot
// make the bounded-queue conservation check pass.
struct EdgeReference {
  enum Level { kUnknown, kLow, kHigh };
  Level level;
  bool count_initial_high;
  explicit EdgeReference(bool count) : level(kUnknown),
      count_initial_high(count) {}
  bool Observe(float value) {
    if (!std::isfinite(value)) { level = kUnknown; return false; }
    if (level == kUnknown) {
      if (value <= 0.0f) { level = kLow; return false; }
      if (value >= 1.0f) { level = kHigh; return count_initial_high; }
      return false;
    }
    if (level == kHigh) {
      if (value <= 0.0f) level = kLow;
      return false;
    }
    if (value >= 1.0f) { level = kHigh; return true; }
    return false;
  }
};

static void EdgeConservation() {
  // An independent state oracle counts acquired rises. Conservation must hold
  // through queue saturation, invalid samples, partial drains, and both
  // initial-high policies.
  const float values[] = {-1.0f, 0.0f, 0.5f, 1.0f, 2.0f,
      std::numeric_limits<float>::quiet_NaN(),
      std::numeric_limits<float>::infinity()};
  for (unsigned policy = 0; policy < 2; ++policy) {
    for (unsigned capacity = 1; capacity <= 7; ++capacity) {
      RisingEdgeCapture<float> actual;
      EdgeReference acquisition(policy != 0);
      const auto p = policy ? HighAcquisitionPolicy::kCountAsRise
                            : HighAcquisitionPolicy::kSeedSilently;
      CHECK(actual.Configure(0.0f, 1.0f, static_cast<uint16_t>(capacity), p));
      uint32_t rng = 0x46524731u;
      unsigned observed = 0, consumed = 0, dropped = 0;
      bool overflow = false;
      for (unsigned i = 0; i < 20000; ++i) {
        const unsigned operation = Next(rng) % 11;
        if (operation < 7) {
          const unsigned before = actual.pending();
          const bool captured = acquisition.Observe(values[operation]);
          const bool accepted = actual.Observe(values[operation]);
          if (captured) {
            ++observed;
            if (before == capacity) { ++dropped; overflow = true; }
          }
          CHECK(accepted == (captured && before < capacity));
          CHECK(actual.level_known() == (acquisition.level != EdgeReference::kUnknown));
          CHECK(actual.high() == (acquisition.level == EdgeReference::kHigh));
        } else if (operation < 10) {
          const uint16_t maximum = static_cast<uint16_t>(operation - 7);
          const unsigned before = actual.pending();
          const unsigned taken = actual.Consume(maximum);
          CHECK(taken == (before < maximum ? before : maximum));
          consumed += taken;
        } else {
          actual.ClearOverflow(); overflow = false;
        }
        CHECK(actual.pending() <= capacity);
        CHECK(actual.overflowed() == overflow);
        CHECK(observed == consumed + dropped + actual.pending());
      }
    }
  }
}

static void DebounceTimeTranslation() {
  // A history-based oracle uses unwrapped 64-bit absolute time. The library
  // sees only translated 32-bit timestamps, including repeated wraparound.
  const uint32_t durations[] = {0, 1, 7, 100, 0x7fffffffu};
  for (uint32_t on : durations) {
    for (uint32_t off : durations) {
      DebouncedButton button;
      CHECK(button.Configure(on, off));
      uint32_t rng = 0x44656231u;
      uint64_t now = 0xfffffff0ull, run_start = 0;
      bool state = false, has_run = false, last_input = false;
      for (unsigned i = 0; i < 10000; ++i) {
        const uint32_t random = Next(rng);
        now += i % 31 == 0 ? uint64_t(0x70000000u) : random % 23;
        const bool valid = (random >> 8) % 7 != 0;
        const bool input = ((random >> 16) & 1u) != 0;
        bool expected_change = false;
        if (!valid || input == state) has_run = false;
        else {
          if (!has_run || last_input != input) run_start = now;
          has_run = true;
          if (now - run_start >= (input ? on : off)) {
            state = input; has_run = false; expected_change = true;
          }
        }
        last_input = input;
        CHECK(button.Observe(input, static_cast<uint32_t>(now), valid) == expected_change);
        CHECK(button.pressed() == state && button.pending() == has_run);
      }
    }
  }
}

static void DebounceBoundaryAndGap() {
  DebouncedButton button;
  const uint32_t maximum = 0x7fffffffu;
  CHECK(button.Configure(maximum, maximum));
  const uint64_t start = 0xfffffff0ull;
  CHECK(!button.Observe(true, static_cast<uint32_t>(start)));
  CHECK(!button.Observe(true, static_cast<uint32_t>(start + 0x70000000ull)));
  CHECK(!button.Observe(true, static_cast<uint32_t>(start + maximum - 1)));
  CHECK(button.Observe(true, static_cast<uint32_t>(start + maximum)));
  CHECK(button.pressed() && !button.pending());

  const uint64_t release = start + maximum + 1;
  CHECK(!button.Observe(false, static_cast<uint32_t>(release)));
  CHECK(!button.Observe(false, static_cast<uint32_t>(release + 0x70000000ull)));
  CHECK(!button.Observe(false, static_cast<uint32_t>(release + maximum - 1)));
  CHECK(button.Observe(false, static_cast<uint32_t>(release + maximum)));
  CHECK(!button.pressed() && !button.pending());

  // Invalid evidence at the old deadline breaks continuity. The next valid
  // sample starts a new candidate, even if its level has not changed.
  CHECK(button.Configure(7, 3));
  const uint64_t gap_start = release + maximum + 1;
  CHECK(!button.Observe(true, static_cast<uint32_t>(gap_start)));
  CHECK(!button.Observe(true, static_cast<uint32_t>(gap_start + 6)));
  CHECK(!button.Observe(true, static_cast<uint32_t>(gap_start + 7), false));
  CHECK(!button.pending() && !button.pressed());
  CHECK(!button.Observe(true, static_cast<uint32_t>(gap_start + 8)));
  CHECK(!button.Observe(true, static_cast<uint32_t>(gap_start + 14)));
  CHECK(button.Observe(true, static_cast<uint32_t>(gap_start + 15)));
  CHECK(!button.Observe(false, static_cast<uint32_t>(gap_start + 16)));
  CHECK(!button.Observe(false, static_cast<uint32_t>(gap_start + 18)));
  CHECK(button.Observe(false, static_cast<uint32_t>(gap_start + 19)));
  CHECK(!button.pressed());
}

static void ControlSweeps() {
  // Order, range, endpoint, and symmetry properties do not depend on copying
  // the transfer formula into a test. Non-default neutral widths are included.
  for (float width : {0.0f, 0.1f, 2.0f, 7.0f, 49.0f}) {
    float last = -100.0f;
    for (unsigned i = 0; i <= 4096; ++i) {
      const float position = static_cast<float>(i) * (100.0f / 4096);
      const float mapped = BipolarAmount(position, width);
      CHECK(std::isfinite(mapped) && mapped >= last && mapped >= -100 && mapped <= 100);
      CHECK(std::fabs(mapped + BipolarAmount(100 - position, width)) < 0.001f);
      last = mapped;
    }
    CHECK(BipolarAmount(0, width) == -100 && BipolarAmount(100, width) == 100);
  }
  for (int steps = 1; steps <= 32; ++steps) {
    int selected = -1;
    for (unsigned i = 0; i <= 4096; ++i) {
      const int next = SelectHysteretic(float(i) / 4096, steps, selected, 0.2f);
      CHECK(next >= selected && next >= 0 && next < steps);
      selected = next;
    }
    CHECK(selected == steps - 1);
    for (int i = 4096; i >= 0; --i) {
      const int next = SelectHysteretic(float(i) / 4096, steps, selected, 0.2f);
      CHECK(next <= selected && next >= 0 && next < steps);
      selected = next;
    }
    CHECK(selected == 0);
  }
}

int main() {
  PresenceWindows(); EdgeConservation(); DebounceTimeTranslation();
  DebounceBoundaryAndGap(); ControlSweeps();
  std::puts("PASS synthetic properties: evidence resets, event conservation, time translation, control sweeps");
}
