// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "eurorack_patterns/controls.h"
#include <algorithm>
#include <cmath>
#include <climits>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <limits>

using namespace eurorack_patterns;
#define CHECK(condition) do { if (!(condition)) { \
  std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
  std::exit(1); } } while (0)

int main() {
  const float nan = std::numeric_limits<float>::quiet_NaN();
  const float inf = std::numeric_limits<float>::infinity();
  // Keep the default mapping's float operation order stable, bit for bit.
  const auto original_amount = [](float position) {
    const float value = 2 * position - 100;
    return std::copysign(std::max(0.0f, std::fabs(value) - 4) * 100 / 96,
                         value);
  };
  for (int i = 0; i <= 1000; ++i) {
    const float position = i * 0.1f;
    const float actual = BipolarAmount(position);
    const float original = original_amount(position);
    CHECK(std::memcmp(&actual, &original, sizeof(float)) == 0);
  }
  unsigned rng = 0x12345678u;
  for (int i = 0; i < 100000; ++i) {
    rng = rng * 1664525u + 1013904223u;
    const float position = (rng % 1000001u) * 0.0001f;
    const float actual = BipolarAmount(position);
    const float original = original_amount(position);
    CHECK(std::memcmp(&actual, &original, sizeof(float)) == 0);
  }
  CHECK(BipolarAmount(48.0f) == 0.0f);
  CHECK(BipolarAmount(52.0f) == 0.0f);
  CHECK(BipolarAmount(0.0f) == -100.0f);
  CHECK(BipolarAmount(100.0f) == 100.0f);
  CHECK(std::isnan(BipolarAmount(nan)));
  CHECK(std::isnan(BipolarAmount(inf)));
  CHECK(BipolarAmount(46.0f, 4.0f) == 0.0f);
  CHECK(BipolarAmount(54.0f, 4.0f) == 0.0f);
  CHECK(BipolarAmount(0.0f, 0.0f) == -100.0f);
  CHECK(BipolarAmount(100.0f, 4.0f) == 100.0f);
  CHECK(std::isnan(BipolarAmount(50.0f, nan)));
  CHECK(std::isnan(BipolarAmount(50.0f, -1.0f)));
  CHECK(std::isnan(BipolarAmount(50.0f, 50.0f)));

  // Generic mapped units: voltage and logarithmic frequency need no percent
  // or bipolar flag. At exactly 0.5, arming is required and near is false.
  CHECK(PickupRequired(-2.0f, 3.0f));
  CHECK(PickupCrossed(-2.0f, 4.0f, 3.0f));
  CHECK(PickupRequired(440.0f, 441.0f, 0.5f));
  CHECK(PickupCrossed(440.0f, 440.8f, 441.0f, 0.5f));
  CHECK(PickupRequired(50.5f, 50.0f));
  CHECK(!PickupCrossed(51.0f, 50.5f, 50.0f));
  CHECK(!PickupRequired(nan, 0.0f));
  CHECK(!PickupCrossed(0.0f, inf, 1.0f));
  CHECK(!PickupCrossed(0.0f, 1.0f, 0.5f, 0.0f));

  // Crossing in both directions, including a skipped target and a reversal.
  float base = 50.0f;
  bool catching = false;
  CHECK(ArmPickup(80.0f, base, false, catching) && catching && base == 50.0f);
  CHECK(!UpdatePickup(80.0f, 70.0f, base, false, catching));
  CHECK(!UpdatePickup(70.0f, 75.0f, base, false, catching));
  CHECK(UpdatePickup(75.0f, 40.0f, base, false, catching));
  CHECK(!catching && base == 40.0f);
  CHECK(UpdatePickup(40.0f, 100.0f, base, false, catching) && base == 100.0f);
  CHECK(ArmPickup(20.0f, base, false, catching) && catching);
  CHECK(UpdatePickup(20.0f, 100.0f, base, false, catching) && !catching);

  // Strict tolerance: equality at 0.5 arms and does not catch until closer.
  base = 50.0f;
  CHECK(ArmPickup(50.5f, base, false, catching) && catching);
  CHECK(!UpdatePickup(51.0f, 50.5f, base, false, catching));
  CHECK(UpdatePickup(50.5f, 50.4f, base, false, catching));
  CHECK(base == 50.4f && !catching);
  CHECK(ArmPickup(50.8f, base, false, catching) && !catching && base == 50.8f);

  // The bipolar plateau is a single target even when raw positions differ.
  base = 49.0f;
  CHECK(ArmPickup(53.0f, base, true, catching) && catching);
  CHECK(UpdatePickup(53.0f, 52.0f, base, true, catching));
  CHECK(base == 52.0f && !catching);
  base = 48.0f;
  CHECK(ArmPickup(52.0f, base, true, catching) && !catching && base == 52.0f);

  // Bad telemetry/config cannot corrupt a pending catch or base.
  base = 40.0f; catching = true;
  CHECK(!ArmPickup(nan, base, false, catching));
  CHECK(!ArmPickup(70.0f, base, false, catching, 0.0f));
  CHECK(!UpdatePickup(70.0f, inf, base, false, catching));
  CHECK(!UpdatePickup(70.0f, 40.0f, base, false, catching, nan));
  CHECK(base == 40.0f && catching);

  // 0.1% noise steps accumulate from the last accepted sample.
  float accepted = 50.0f;
  for (int i = 1; i <= 5; ++i)
    CHECK(!AcceptMotion(50.0f + i * 0.1f, accepted));
  CHECK(accepted == 50.0f);
  CHECK(AcceptMotion(50.7f, accepted) && accepted == 50.7f);
  CHECK(!AcceptMotion(51.0f, accepted));
  CHECK(AcceptMotion(51.4f, accepted));
  accepted = 0.4f;
  CHECK(AcceptMotion(0.0f, accepted) && accepted == 0.0f);
  accepted = 99.7f;
  CHECK(AcceptMotion(100.0f, accepted) && accepted == 100.0f);
  CHECK(!AcceptMotion(nan, accepted));
  CHECK(!AcceptMotion(90.0f, accepted, inf));
  CHECK(accepted == 100.0f);

  // Noisy, slow sweep: tiny reversals must not reset the accepted anchor.
  // Keep two controls independent, as a caller's parallel arrays do.
  float physical[2] = {50.0f, 75.0f};
  float held[2] = {50.0f, 25.0f};
  bool armed[2] = {false, false};
  CHECK(ArmPickup(physical[1], held[1], false, armed[1]) && armed[1]);
  const float trace[] = {50.1f, 50.2f, 50.1f, 50.3f, 50.4f,
                         50.3f, 50.5f, 50.6f, 50.7f};
  int accepted_count = 0;
  for (unsigned i = 0; i < sizeof(trace) / sizeof(trace[0]); ++i) {
    const float previous = physical[0];
    if (AcceptMotion(trace[i], physical[0])) {
      ++accepted_count;
      CHECK(UpdatePickup(previous, physical[0], held[0], false, armed[0]));
    }
  }
  CHECK(accepted_count == 1 && physical[0] == 50.7f && held[0] == 50.7f);
  CHECK(physical[1] == 75.0f && held[1] == 25.0f && armed[1]);

  // Selector boundaries are sticky; invalid readings preserve selection.
  CHECK(SelectHysteretic(0.0f, 4, -1, 0.05f) == 0);
  CHECK(SelectHysteretic(1.0f, 4, -1, 0.05f) == 3);
  CHECK(SelectHysteretic(0.251f, 4, 0, 0.05f) == 0);
  CHECK(SelectHysteretic(0.27f, 4, 0, 0.05f) == 1);
  CHECK(SelectHysteretic(0.249f, 4, 1, 0.05f) == 1);
  CHECK(SelectHysteretic(0.23f, 4, 1, 0.05f) == 0);
  CHECK(SelectHysteretic(0.251f, 4, 0, -1.0f) == 1);
  CHECK(SelectHysteretic(nan, 4, 2, 0.05f) == 2);
  CHECK(SelectHysteretic(0.3f, 0, 2, 0.05f) == 2);
  CHECK(SelectHysteretic(0.3f, 4, 2, 0.5f) == 2);
  CHECK(SelectHysteretic(1.0f, INT_MAX, INT_MAX - 2, 0.0f) == INT_MAX - 1);
  std::puts("PASS controls");
}
