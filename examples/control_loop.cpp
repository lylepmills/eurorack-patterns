// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include <eurorack_patterns/controls.h>
#include <eurorack_patterns/events.h>
#include <eurorack_patterns/gestures.h>
#include <eurorack_patterns/presence.h>
#include <eurorack_patterns/timing.h>
#include <eurorack_patterns/transitions.h>
#include <cstdio>

// Synthetic host example. Hardware adapters supply fresh acquisitions and time.
// All operations here share one owner; an ISR handoff needs synchronization.
int main() {
  using namespace eurorack_patterns;
  float physical = 80, stored = 30;
  bool catching = false;
  if (!ArmPickup(physical, stored, false, catching)) return 1;
  const float samples[] = {79.9f, 70, 50, 20};
  for (float next : samples) {
    const float previous = physical;
    if (AcceptMotion(next, physical))
      UpdatePickup(previous, physical, stored, false, catching);
  }
  if (catching || stored != 20) return 1;

  PresenceDetector jack;
  // Demo counts only: choose cadence and qualification using your own circuit.
  if (!jack.Configure({4, 2, 3, PresenceStartupPolicy::kRequireStreak}, {false, false})) return 1;
  jack.Observe(PresenceEvidence::kInvalid); // never score retained/stale voltage
  for (int n=0; n<12; ++n) jack.Observe(PresenceEvidence::kMismatch);
  if (!jack.ready() || !jack.patched()) return 1;

  RisingEdgeCapture<float> trigger;
  if (!trigger.Configure(0.1f, 0.8f, 16, HighAcquisitionPolicy::kSeedSilently)) return 1;
  const float pulse_samples[] = {0, 1, 0, 1, 0};
  for (float value : pulse_samples) trigger.Observe(value);
  if (trigger.Consume(16) != 2) return 1;

  enum class Role { Modifier, Back };
  RoleLatch<Role> button;
  button.Press(Role::Modifier);
  button.Consume(); // combination handled; end modifier now, then navigate
  Role released = Role::Back;
  if (button.Release(released)) return 1; // physical release performs no second action

  LatestRequest<unsigned> presets;
  presets.Request(4); presets.Request(9);
  unsigned next = 0;
  if (!presets.Take(next) || next != 9) return 1; // caller chose a safe boundary
  std::puts("PASS: portable control loop");
}
