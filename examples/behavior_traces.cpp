// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include <eurorack_patterns/presence.h>
#include <eurorack_patterns/pickup.h>
#include <eurorack_patterns/gestures.h>
#include <cstdio>
#include <cstdlib>
#define CHECK(x) do { if (!(x)) std::exit(1); } while (0)
int main() {
  using namespace eurorack_patterns;
  std::puts("pattern,step,direct,qualified");
  PresenceDetector presence;
  CHECK(presence.Configure({4, 2, 2, PresenceStartupPolicy::kRequireStreak}, {true, false}));
  const int mismatch[] = {0,0,0,0,1,0,1,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1};
  for (int i = 0; i < 24; ++i) {
    presence.Observe(mismatch[i] ? PresenceEvidence::kMismatch : PresenceEvidence::kMatch);
    CHECK(presence.patched() == (i >= 19));
    std::printf("presence,%d,%d,%d\n", i, mismatch[i], presence.patched() ? 1 : 0);
  }
  PickupLatch pickup;
  CHECK(pickup.Configure(0, 100, 0.5f) && pickup.Arm(30));
  const int samples[] = {80,80,70,60,50,40,20,10};
  float stored = 30;
  for (int i = 0; i < 8; ++i) {
    if (pickup.Observe(static_cast<float>(samples[i]))) stored = static_cast<float>(samples[i]);
    CHECK(stored == (i < 6 ? 30 : samples[i]));
    std::printf("pickup,%d,%d,%.0f\n", i, samples[i], stored);
  }
  enum class Role { Edit };
  RoleLatch<Role> gesture;
  int direct_actions = 0, owned_actions = 0;
  for (int i = 0; i < 6; ++i) {
    if (i == 1) CHECK(gesture.Press(Role::Edit));
    if (i == 3) { CHECK(gesture.Consume()); ++direct_actions; ++owned_actions; }
    if (i == 4) {
      Role role = Role::Edit;
      ++direct_actions;
      if (gesture.Release(role)) ++owned_actions;
    }
    CHECK(owned_actions == (i >= 3 ? 1 : 0));
    std::printf("gesture,%d,%d,%d\n", i, direct_actions, owned_actions);
  }
  CHECK(direct_actions == 2 && owned_actions == 1);
}
