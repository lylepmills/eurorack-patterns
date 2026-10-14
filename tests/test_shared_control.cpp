// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "../examples/shared_control.h"
#include <cstdio>
#include <cstdlib>
#include <limits>
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)
using State = eurorack_patterns::PickupLatch::State;
int main() {
  example::SharedControl c;
  CHECK(c.Reset(0.5f));
  CHECK(!c.Sample(80, true));
  CHECK(!c.Sample(79.8f, true));
  CHECK(c.Sample(40, true) && c.value() == 0.4f);
  CHECK(!c.Sample(39.8f, true)); // Rejected movement never moves the anchor.
  CHECK(!c.Sample(39.6f, true));
  CHECK(c.Sample(39.0f, true));
  CHECK(c.Sample(0, true) && c.value() == 0.0f);
  CHECK(c.Sample(100, true) && c.value() == 1.0f);
  CHECK(c.ExternalEdit(0.5f));
  CHECK(!c.Sample(100, true));
  CHECK(!c.Sample(100, false)); // A stale equal value must still break history.
  CHECK(!c.Sample(20, true) && c.state() == State::kWaiting);
  CHECK(c.Sample(80, true));
  CHECK(c.ExternalEdit(0.5f));
  CHECK(!c.Sample(std::numeric_limits<float>::quiet_NaN(), true));
  CHECK(!c.Sample(20, true));
  CHECK(!c.Sample(-1, true));
  CHECK(!c.Sample(80, true));
  CHECK(c.Sample(20, true));
  CHECK(c.ExternalEdit(0.2f)); // Already near: no unnecessary dead control.
  CHECK(c.state() == State::kTracking);
  CHECK(c.Sample(21, true));
  CHECK(!c.ExternalEdit(2.0f) && !c.Reset(-1.0f));
  CHECK(c.state() == State::kTracking && c.value() == 0.21f);
  CHECK(c.Reset(0.5f));
  CHECK(!c.Sample(80, true)); // Reset erased previous crossing history.
  CHECK(c.Sample(20, true));
  // Every sample in a fresh slow sweep eventually contributes to motion.
  CHECK(c.Reset(0));
  c.Sample(0, true);
  for (int i = 1; i <= 1000; ++i) c.Sample(i / 10.0f, true);
  CHECK(c.value() == 1.0f);
  std::puts("PASS: shared-control application regression");
}
