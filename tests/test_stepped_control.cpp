// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
// Synthetic application-policy tests; no physical input or control-feel claim.
#include "../examples/stepped_control.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <initializer_list>
#include <limits>

#define CHECK(x) do { if (!(x)) { \
  std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); std::exit(1); \
} } while (0)

namespace {
const float kValues[] = {0.0f, 0.25f, 0.5f, 0.75f, 1.0f};

// Independent finite-set oracle: enumerate distances, rather than use the
// adapter's midpoint thresholds, scaling or PickupLatch implementation.
int Nearest(float sample) {
  int best = 0;
  double distance = std::numeric_limits<double>::infinity();
  for (int i = 0; i < 5; ++i) {
    const double candidate = std::fabs(static_cast<double>(sample) - kValues[i]);
    if (candidate <= distance) { best = i; distance = candidate; }
  }
  return best;  // Equal distance selects the higher member.
}

struct Destination {
  explicit Destination(float initial) : stored(initial) {}
  float ReadNormalized() const { return stored; }
  void WriteNormalized(float requested) {
    ++writes;
    if (!reject) stored = override_write ? forced : kValues[Nearest(requested)];
  }
  float stored;
  unsigned writes = 0;
  bool reject = false;
  bool override_write = false;
  float forced = 0.0f;
};
using Control = example::SteppedControl<Destination>;
using State = Control::State;
using Result = Control::WriteResult;

struct Oracle {
  explicit Oracle(float initial) { Rearm(initial); }
  void Rearm(float stored) {
    value = stored;
    previous = -1;
    target = -1;
    for (int i = 0; i < 5; ++i) if (stored == kValues[i]) target = i;
    state = target < 0 ? State::kUnreachable : State::kWaiting;
  }
  bool Sample(float sample, bool valid) {
    if (!valid || !std::isfinite(sample) || sample < 0.0f || sample > 1.0f) {
      previous = -1;
      return false;
    }
    if (target < 0) return false;
    const int current = Nearest(sample);
    bool visited_target = current == target;
    // Enumerate every member traversed by this uninterrupted pair. No near
    // tolerance or sign-straddle expression from the implementation is reused.
    if (previous >= 0) {
      for (int i = previous; i != current; i += current > previous ? 1 : -1)
        if (i == target) visited_target = true;
    }
    previous = current;
    if (state != State::kTracking && !visited_target) return false;
    state = State::kTracking;
    value = kValues[current];
    ++writes;
    return true;
  }
  float value = 0.0f;
  int target = -1;
  int previous = -1;
  State state = State::kUnreachable;
  unsigned writes = 0;
};

void CheckSample(Control& control, Destination& destination, Oracle& oracle,
                 float sample, bool valid = true) {
  const Result expected = oracle.Sample(sample, valid) ? Result::kMatched : Result::kNone;
  CHECK(control.Sample(sample, valid) == expected);
  CHECK(control.state() == oracle.state);
  CHECK(control.value() == oracle.value);
  CHECK(destination.stored == oracle.value && destination.writes == oracle.writes);
}

void FiniteSequences() {
  const float targets[] = {0.0f, 0.25f, 0.5f, 0.75f, 1.0f, 0.4f};
  unsigned traces = 0;
  for (float target : targets) {
    // All 6^4 traces over the five steps plus an invalid sample. This includes
    // coarse skips, both directions, endpoints, gaps and immediate reversals.
    for (unsigned trace = 0; trace < 1296; ++trace) {
      Destination destination(target);
      Control control(destination);
      Oracle oracle(target);
      unsigned remaining = trace;
      for (int tick = 0; tick < 4; ++tick) {
        const unsigned symbol = remaining % 6;
        remaining /= 6;
        CheckSample(control, destination, oracle,
                    symbol < 5 ? kValues[symbol] : 0.5f, symbol < 5);
      }
      ++traces;
    }
  }
  CHECK(traces == 7776);
}

void SweepsAndBoundaries() {
  for (float target : kValues) {
    for (int direction : {-1, 1}) {
      Destination destination(target);
      Control control(destination);
      Oracle oracle(target);
      for (int tick = 0; tick <= 1024; ++tick) {
        const int position = direction > 0 ? tick : 1024 - tick;
        CheckSample(control, destination, oracle, static_cast<float>(position) / 1024.0f);
      }
      CHECK(control.state() == State::kTracking);
    }
    for (float midpoint : {0.125f, 0.375f, 0.625f, 0.875f}) {
      for (float sample : {std::nextafter(midpoint, 0.0f), midpoint,
                           std::nextafter(midpoint, 1.0f)}) {
        Destination destination(target);
        Control control(destination);
        Oracle oracle(target);
        CheckSample(control, destination, oracle, sample);
      }
    }
  }
  // Quantized matching, not raw-position matching: .44 already reaches .5.
  Destination destination(0.5f);
  Control control(destination);
  CHECK(control.Sample(0.44f, true) == Result::kMatched);
  CHECK(control.value() == 0.5f);
  CHECK(control.Sample(0.8f, true) == Result::kMatched);
  CHECK(control.value() == 0.75f);
}

void OwnershipAndGaps() {
  Destination destination(0.5f);
  Control control(destination);
  Oracle oracle(0.5f);
  // Rearming every possible pair clears both waiting and tracking history.
  for (float first : kValues) {
    for (float target : kValues) {
      destination.stored = 0.5f;
      CHECK(control.Rearm());
      oracle.Rearm(0.5f);
      CheckSample(control, destination, oracle, first);
      destination.stored = target;
      CHECK(control.Rearm());
      oracle.Rearm(target);
      CHECK(control.state() == State::kWaiting);
      CheckSample(control, destination, oracle, 1.0f - first);
      CheckSample(control, destination, oracle, target);
    }
  }
  const float nan = std::numeric_limits<float>::quiet_NaN();
  const float inf = std::numeric_limits<float>::infinity();
  for (float bad : {nan, inf, -inf, -0.01f, 1.01f}) {
    destination.stored = 0.5f;
    CHECK(control.Rearm());
    oracle.Rearm(0.5f);
    CheckSample(control, destination, oracle, 0.0f);
    CheckSample(control, destination, oracle, bad);
    CheckSample(control, destination, oracle, 1.0f);
    CHECK(control.state() == State::kWaiting);
    CheckSample(control, destination, oracle, 0.0f);
    CHECK(control.state() == State::kTracking);
    CheckSample(control, destination, oracle, bad);
    CHECK(control.state() == State::kTracking);  // Gap suppresses writes, not ownership.
    CheckSample(control, destination, oracle, 1.0f);
  }
}

void UnreachableAndReadback() {
  const float nan = std::numeric_limits<float>::quiet_NaN();
  const float inf = std::numeric_limits<float>::infinity();
  for (float stored : {0.4f, 0.125f, -0.25f, 1.25f, nan, inf}) {
    Destination destination(0.5f);
    Control control(destination);
    CHECK(control.Sample(0.5f, true) == Result::kMatched);
    destination.stored = stored;
    CHECK(!control.Rearm());  // Bad external state must revoke previous ownership.
    CHECK(control.state() == State::kUnreachable);
    CHECK(std::isnan(stored) ? std::isnan(control.value()) : control.value() == stored);
    const unsigned writes = destination.writes;
    for (float sample : kValues) CHECK(control.Sample(sample, true) == Result::kNone);
    CHECK(destination.writes == writes);
    destination.stored = 0.75f;  // Explicit recovery; never silently snap saved state.
    CHECK(control.Rearm() && control.state() == State::kWaiting);
    CHECK(control.Sample(0.0f, true) == Result::kNone);
    CHECK(control.Sample(0.75f, true) == Result::kMatched);
  }

  Destination destination(0.5f);
  Control control(destination);
  CHECK(control.Sample(0.5f, true) == Result::kMatched);
  destination.reject = true;
  CHECK(control.Sample(0.9f, true) == Result::kMismatch);
  CHECK(control.value() == 0.5f && control.state() == State::kWaiting);
  const unsigned writes = destination.writes;
  CHECK(control.Sample(0.0f, true) == Result::kNone);  // No stale crossing after rejection.
  CHECK(destination.writes == writes);
  destination.reject = false;
  destination.override_write = true;
  destination.forced = 0.25f;
  CHECK(control.Sample(1.0f, true) == Result::kMismatch);
  CHECK(control.value() == 0.25f && control.state() == State::kWaiting);
  CHECK(control.Sample(1.0f, true) == Result::kNone);
  destination.forced = 0.4f;
  CHECK(control.Sample(0.0f, true) == Result::kMismatch);
  CHECK(control.value() == 0.4f && control.state() == State::kUnreachable);
  CHECK(control.Sample(0.5f, true) == Result::kNone);
  destination.stored = 0.5f;
  CHECK(control.Rearm());
  destination.forced = nan;
  CHECK(control.Sample(0.5f, true) == Result::kMismatch);
  CHECK(std::isnan(control.value()) && control.state() == State::kUnreachable);
}
}  // namespace

int main() {
  FiniteSequences();
  SweepsAndBoundaries();
  OwnershipAndGaps();
  UnreachableAndReadback();
  std::puts("PASS: 7776 finite-set traces, sweeps, boundaries, ownership, gaps and readback");
}
