// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "eurorack_patterns/pickup.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>

using eurorack_patterns::PickupLatch;
using State = PickupLatch::State;

#define CHECK(condition) do { if (!(condition)) { \
  std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
  std::exit(1); } } while (0)

int main() {
  const float nan = std::numeric_limits<float>::quiet_NaN();
  const float inf = std::numeric_limits<float>::infinity();

  PickupLatch latch;
  CHECK(!latch.configured() && latch.state() == State::kUnarmed);
  CHECK(!latch.Arm(0.5f));
  CHECK(!latch.Observe(0.5f));
  CHECK(latch.Configure(0.2f, 0.8f, 0.01f));
  CHECK(latch.configured() && latch.state() == State::kUnarmed);

  // A restricted range reports an impossible stored target immediately.
  CHECK(latch.Arm(0.9f));
  CHECK(latch.state() == State::kUnreachable);
  CHECK(!latch.Observe(0.8f));
  CHECK(!latch.Observe(0.9f));  // Outside the configured sample interval.
  CHECK(latch.Arm(0.5f) && latch.state() == State::kWaiting);
  CHECK(!latch.Observe(0.2f));
  CHECK(latch.Observe(0.8f));   // Skipped target on a coarse scan.
  CHECK(latch.state() == State::kTracking);
  CHECK(latch.Observe(0.8f));   // Permission is not a changed-value event.
  CHECK(latch.Observe(0.3f));

  // The same contract works for reversed endpoints and either sweep direction.
  CHECK(latch.Configure(0.8f, 0.2f, 0.01f));
  CHECK(latch.Arm(0.5f));
  CHECK(!latch.Observe(0.8f));
  CHECK(latch.Observe(0.2f));
  CHECK(latch.Arm(0.5f));
  CHECK(!latch.Observe(0.2f));
  CHECK(latch.Observe(0.8f));
  CHECK(latch.Arm(0.9f) && latch.state() == State::kUnreachable);

  // A zero-width mapping can pick up only its single reachable value.
  CHECK(latch.Configure(0.5f, 0.5f, 0.1f));
  CHECK(latch.Arm(0.5f) && latch.state() == State::kWaiting);
  CHECK(!latch.Observe(0.4f));
  CHECK(latch.Observe(0.5f));
  CHECK(latch.Arm(0.6f) && latch.state() == State::kUnreachable);

  // Invalid samples break the crossing pair. They never tear down an arm.
  CHECK(latch.Configure(-1.0f, 1.0f, 0.01f));
  CHECK(latch.Arm(0.0f));
  CHECK(!latch.Observe(-0.8f));
  CHECK(!latch.Observe(0.0f, false));
  CHECK(!latch.Observe(0.8f));  // No phantom crossing over the invalid gap.
  CHECK(latch.state() == State::kWaiting);
  CHECK(!latch.Observe(nan));
  CHECK(!latch.Observe(-0.8f));
  CHECK(!latch.Observe(2.0f));  // Finite but outside range also breaks history.
  CHECK(!latch.Observe(0.8f));
  CHECK(!latch.Observe(inf));
  CHECK(!latch.Observe(-0.8f));
  CHECK(latch.Observe(0.8f));
  CHECK(latch.state() == State::kTracking);
  CHECK(!latch.Observe(nan));
  CHECK(latch.state() == State::kTracking);
  CHECK(latch.Observe(0.0f));

  // Near matching is strict, and a first valid near sample can catch.
  CHECK(latch.Configure(0.0f, 1.0f, 0.125f));
  CHECK(latch.Arm(0.5f));
  CHECK(!latch.Observe(0.625f));
  CHECK(latch.Observe(0.6f));
  CHECK(latch.Arm(0.0f));
  CHECK(latch.Observe(0.0f));  // Endpoint target is valid.
  CHECK(latch.Arm(1.0f));
  CHECK(!latch.Observe(0.0f));
  CHECK(latch.Observe(1.0f));

  // Rearming starts a new ownership epoch, with no inherited crossing pair.
  CHECK(latch.Arm(0.7f) && latch.state() == State::kWaiting);
  CHECK(!latch.Observe(0.9f));
  CHECK(latch.Observe(0.6f));

  // Rejected configuration and arm preserve waiting history as well as state.
  CHECK(latch.Arm(0.5f));
  CHECK(!latch.Observe(0.2f));
  CHECK(!latch.Configure(nan, 1.0f, 0.1f));
  CHECK(!latch.Arm(nan));
  CHECK(latch.state() == State::kWaiting);
  CHECK(latch.Observe(0.8f));

  // A bad configuration or arm cannot silently erase a working latch.
  CHECK(!latch.Configure(nan, 1.0f, 0.1f));
  CHECK(!latch.Configure(0.0f, inf, 0.1f));
  CHECK(!latch.Configure(0.0f, 1.0f, nan));
  CHECK(!latch.Configure(0.0f, 1.0f, 0.0f));
  CHECK(!latch.Configure(0.0f, 1.0f, -0.1f));
  CHECK(!latch.Arm(inf));
  CHECK(latch.state() == State::kTracking && latch.Observe(0.8f));
  latch.Disarm();
  CHECK(latch.configured() && latch.state() == State::kUnarmed);
  CHECK(!latch.Observe(0.5f));
  CHECK(latch.Arm(0.5f) && latch.state() == State::kWaiting);

  // Deterministic sweeps: every in-range target is crossed from either side,
  // while targets outside the range never gain apply permission.
  for (int i = 0; i < 100; ++i) {
    const float low = static_cast<float>(i) * 0.1f;
    const float high = low + 1.0f;
    const float target = low + 0.37f;
    PickupLatch ascending;
    PickupLatch descending;
    CHECK(ascending.Configure(low, high, 0.001f));
    CHECK(descending.Configure(high, low, 0.001f));
    CHECK(ascending.Arm(target) && descending.Arm(target));
    CHECK(!ascending.Observe(low) && !descending.Observe(high));
    CHECK(ascending.Observe(high) && descending.Observe(low));
    CHECK(ascending.state() == State::kTracking);
    CHECK(descending.state() == State::kTracking);
    CHECK(ascending.Arm(high + 0.1f));
    CHECK(ascending.state() == State::kUnreachable);
    CHECK(!ascending.Observe(high));
  }

  std::puts("PASS pickup");
}
