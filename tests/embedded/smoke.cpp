// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include <eurorack_patterns/controls.h>
#include <eurorack_patterns/events.h>
#include <eurorack_patterns/gestures.h>
#include <eurorack_patterns/pickup.h>
#include <eurorack_patterns/presence.h>
#include <eurorack_patterns/pulses.h>
#include <eurorack_patterns/timing.h>
#include <eurorack_patterns/transitions.h>
#include <eurorack_patterns/trigger_delay.h>
#include "../../examples/shared_control.h"

// Compile and instantiate all nine headers for ARM; this is not an execution test.
extern "C" unsigned patterns_arm_smoke(float input, uint32_t now) {
  using namespace eurorack_patterns;
  PresenceDetector presence;
  presence.Configure({4, 2, 2, PresenceStartupPolicy::kRequireStreak}, {true, false});
  presence.Observe(input > 0 ? PresenceEvidence::kMismatch : PresenceEvidence::kMatch);
  RisingEdgeCapture<float> edges;
  edges.Configure(0, 1, 4, HighAcquisitionPolicy::kCountAsRise);
  edges.Observe(input);
  RoleLatch<unsigned> role;
  role.Press(1); role.Consume();
  unsigned released = 0;
  role.Release(released);
  DebouncedButton button;
  button.Configure(2, 3);
  button.Observe(input > 0, now);
  PickupLatch pickup;
  pickup.Configure(0, 1, 0.01f); pickup.Arm(0.5f);
  PulseTimer pulse;
  pulse.Configure(3, PulseRetriggerPolicy::kRestart); pulse.Trigger(now);
  TriggerDelay<8> delay;
  delay.Schedule(1, 2);
  LatestRequest<unsigned> request;
  request.Request(2); request.Take(released);
  example::SharedControl control;
  control.Reset(0.5f); control.Sample(input, true);
  float accepted = 0;
  AcceptMotion(input, accepted);
  return released + edges.Consume(4) + delay.Tick() + presence.patched() +
      pickup.Observe(input) + pulse.active() + button.pressed() +
      static_cast<unsigned>(SelectHysteretic(input, 8, -1, 0.1f));
}
