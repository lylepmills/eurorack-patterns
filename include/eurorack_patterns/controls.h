// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EURORACK_PATTERNS_CONTROLS_H_
#define EURORACK_PATTERNS_CONTROLS_H_

#include <algorithm>
#include <cmath>

namespace eurorack_patterns {

// Positions and base values are in percent of physical travel, [0, 100].
inline bool ValidPercent(float value) {
  return std::isfinite(value) && value >= 0.0f && value <= 100.0f;
}

// Bipolar amount: the default 48..52% is one neutral point;
// endpoints are +/-100. neutral_halfwidth is in physical percentage points.
// Invalid input or halfwidth outside [0, 50) returns NaN.
inline float BipolarAmount(float position, float neutral_halfwidth = 2.0f) {
  if (!ValidPercent(position) || !std::isfinite(neutral_halfwidth) ||
      neutral_halfwidth < 0.0f || neutral_halfwidth >= 50.0f)
    return std::nanf("");
  const float centered = 2.0f * position - 100.0f;
  // Keep the multiply-then-divide order for stable floating-point results.
  return std::copysign(std::max(0.0f, std::fabs(centered) -
                                       2.0f * neutral_halfwidth)
                           * 100.0f / (100.0f - 2.0f * neutral_halfwidth),
                       centered);
}

inline float PickupValue(float position, bool bipolar) {
  return bipolar ? BipolarAmount(position) : position;
}

// General pickup decisions in any caller-mapped, consistent finite units.
// Invalid readings or tolerance return false. A target at exactly tolerance
// requires pickup; catching nearby is strict (< tolerance).
inline bool PickupRequired(float physical, float target,
                           float tolerance = 0.5f) {
  return std::isfinite(physical) && std::isfinite(target) &&
         std::isfinite(tolerance) && tolerance > 0.0f &&
         std::fabs(target - physical) >= tolerance;
}

// A catch occurs on a crossing (including a skipped target), or sufficiently
// near the target. The values must all be in the same mapped domain.
inline bool PickupCrossed(float previous, float current, float target,
                          float tolerance = 0.5f) {
  if (!std::isfinite(previous) || !std::isfinite(current) ||
      !std::isfinite(target) || !std::isfinite(tolerance) ||
      tolerance <= 0.0f) return false;
  const float before = previous - target;
  const float after = current - target;
  return std::fabs(after) < tolerance ||
         ((before < 0.0f) != (after < 0.0f));
}

// On entering a mode, arm pickup if the knob differs from the stored value by
// at least tolerance in the effective domain. A near knob becomes the value.
// Invalid inputs/configuration leave both outputs unchanged and return false.
inline bool ArmPickup(float physical, float& base, bool bipolar,
                      bool& catching, float tolerance = 0.5f) {
  if (!ValidPercent(physical) || !ValidPercent(base) ||
      !std::isfinite(tolerance) || tolerance <= 0.0f) return false;
  catching = PickupRequired(PickupValue(physical, bipolar),
                            PickupValue(base, bipolar), tolerance);
  if (!catching) base = physical;
  return true;
}

// Call after a physical sample has passed AcceptMotion, passing its previous
// accepted position. Return true when the base or catching state changes. A catch
// accepts a near target (< tolerance) or a crossing, including a skipped target.
// Invalid inputs/configuration leave state unchanged and return false.
inline bool UpdatePickup(float previous, float current, float& base,
                         bool bipolar, bool& catching,
                         float tolerance = 0.5f) {
  if (!ValidPercent(previous) || !ValidPercent(current) ||
      !ValidPercent(base) || !std::isfinite(tolerance) ||
      tolerance <= 0.0f) return false;
  if (!catching) {
    if (base == current) return false;
    base = current;
    return true;
  }
  if (PickupCrossed(PickupValue(previous, bipolar),
                    PickupValue(current, bipolar), PickupValue(base, bipolar),
                    tolerance)) {
    base = current;
    catching = false;
    return true;
  }
  return false;
}

// Filter ADC jitter against the last ACCEPTED position. Rejected samples do
// not move that anchor, so slow motion accumulates. Either endpoint is immediate.
// The caller seeds accepted at startup from a valid initial physical sample.
inline bool AcceptMotion(float candidate, float& accepted,
                         float threshold = 0.6f) {
  if (!ValidPercent(candidate) || !ValidPercent(accepted) ||
      !std::isfinite(threshold) || threshold <= 0.0f) return false;
  if (candidate == accepted) return false;
  if (std::fabs(candidate - accepted) < threshold &&
      candidate != 0.0f && candidate != 100.0f) return false;
  accepted = candidate;
  return true;
}

// Discrete selector with a symmetric dead band at each step boundary.
// normalized is [0,1], hysteresis is in steps [0,0.5); negative disables it.
// previous is the previous selected index, or -1 to initialize without history.
// Invalid input/configuration returns previous unchanged. No allocation/state.
inline int SelectHysteretic(float normalized, int steps, int previous,
                            float hysteresis) {
  if (!std::isfinite(normalized) || normalized < 0.0f ||
      normalized > 1.0f || steps <= 0 ||
      !std::isfinite(hysteresis) || hysteresis >= 0.5f ||
      (previous < -1 || previous >= steps)) return previous;
  const double scaled = static_cast<double>(normalized) * steps;
  int plain = static_cast<int>(std::floor(scaled < steps ? scaled : steps - 1.0));
  if (plain < 0) plain = 0;
  if (previous < 0 || hysteresis < 0.0f) return plain;
  // Nearest-centre selector with a directional dead band.
  const double center = scaled - 0.5;
  const double shifted = center + (center > previous ? -hysteresis : hysteresis);
  int selected = static_cast<int>(std::trunc(shifted + 0.5));
  if (selected < 0) selected = 0;
  if (selected >= steps) selected = steps - 1;
  return selected;
}

}  // namespace eurorack_patterns
#endif  // EURORACK_PATTERNS_CONTROLS_H_
