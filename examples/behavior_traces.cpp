// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
// Synthetic sequences behind the README and gallery pictures. Every block
// checks its expected values, so this program is a test as well as a trace
// source. Counts, thresholds, delays and durations are illustrative; nothing
// here is a hardware recording or a recommended tuning constant.
#include <eurorack_patterns/presence.h>
#include <eurorack_patterns/pickup.h>
#include <eurorack_patterns/gestures.h>
#include <eurorack_patterns/trigger_delay.h>
#include <eurorack_patterns/events.h>
#include <eurorack_patterns/controls.h>
#include <eurorack_patterns/timing.h>
#include <eurorack_patterns/transitions.h>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#define CHECK(x) do { if (!(x)) { \
  std::fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #x); \
  std::exit(1); } } while (0)

static int CountBits(uint32_t mask) {
  int count = 0;
  for (; mask != 0; mask &= mask - 1) ++count;
  return count;
}

int main() {
  using namespace eurorack_patterns;
  std::puts("pattern,step,direct,qualified");

  // Presence: individual probe mismatches versus qualified presence.
  PresenceDetector presence;
  CHECK(presence.Configure({4, 2, 2, PresenceStartupPolicy::kRequireStreak}, {true, false}));
  const int mismatch[] = {0,0,0,0,1,0,1,0,0,0,0,0,1,1,1,1,1,1,1,1,1,1,1,1};
  for (int i = 0; i < 24; ++i) {
    presence.Observe(mismatch[i] ? PresenceEvidence::kMismatch : PresenceEvidence::kMatch);
    CHECK(presence.patched() == (i >= 19));
    std::printf("presence,%d,%d,%d\n", i, mismatch[i], presence.patched() ? 1 : 0);
  }

  // Pickup: direct assignment versus holding the stored value until a crossing.
  PickupLatch pickup;
  CHECK(pickup.Configure(0, 100, 0.5f) && pickup.Arm(30));
  const int samples[] = {80,80,70,60,50,40,20,10};
  float stored = 30;
  for (int i = 0; i < 8; ++i) {
    if (pickup.Observe(static_cast<float>(samples[i]))) stored = static_cast<float>(samples[i]);
    CHECK(stored == (i < 6 ? 30 : samples[i]));
    std::printf("pickup,%d,%d,%.0f\n", i, samples[i], stored);
  }

  // Gesture: a modifier edit plus its release action versus a consumed gesture.
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

  // Trigger delay: A at tick 0 and B at tick 1, both delayed three ticks. The
  // naive model keeps one shared pending mask and deadline, so B overwrites A.
  TriggerDelay<3> delay;
  uint32_t naive_mask = 0;
  int naive_due = -1, naive_delivered = 0, delivered = 0;
  for (int tick = 0; tick <= 6; ++tick) {
    if (tick <= 1) {
      const uint32_t input = tick == 0 ? 0x1u : 0x2u;
      naive_mask = input;
      naive_due = tick + 3;
      CHECK(delay.Schedule(input, 3));
    }
    if (tick == naive_due) { naive_delivered += CountBits(naive_mask); naive_mask = 0; }
    const uint32_t due = delay.Tick();
    CHECK(due == (tick == 3 ? 0x1u : tick == 4 ? 0x2u : 0u));
    delivered += CountBits(due);
    CHECK(naive_delivered == (tick >= 4 ? 1 : 0));
    CHECK(delivered == (tick >= 4 ? 2 : tick == 3 ? 1 : 0));
    std::printf("trigger_delay,%d,%d,%d\n", tick, naive_delivered, delivered);
  }

  // Edge events: four two-sample pulses while the consumer reads every third
  // sample. Polling the level at consume time sees two; the pending count
  // captured at the acquisition rate delivers all four.
  RisingEdgeCapture<int> edges;
  CHECK(edges.Configure(0, 1, 8, HighAcquisitionPolicy::kSeedSilently));
  const int level[] = {0,1,1,0,0,0,1,1,0,0,1,1,0,0,0,1,1,0};
  const int expected_polled[] = {0,0,1,1,1,1,1,1,1,1,1,2,2,2,2,2,2,2};
  const int expected_captured[] = {0,0,1,1,1,1,1,1,2,2,2,3,3,3,3,3,3,4};
  int polled = 0, captured = 0;
  bool polled_high = false;
  for (int i = 0; i < 18; ++i) {
    edges.Observe(level[i]);
    if (i % 3 == 2) {  // The consumer's turn.
      if (level[i] && !polled_high) ++polled;
      polled_high = level[i] != 0;
      captured += edges.Consume(8);
    }
    CHECK(polled == expected_polled[i] && captured == expected_captured[i]);
    std::printf("events,%d,%d,%d\n", i, polled, captured);
  }
  CHECK(polled == 2 && captured == 4 && !edges.overflowed());

  // Hysteretic selection: a four-step selector reads a noisy value hovering
  // within 0.03 of the boundary between steps 1 and 2, then moves to 0.65.
  // Plain truncation flickers; a 0.2-step dead band holds, then follows.
  const float reading[] = {0.40f,0.44f,0.47f,0.49f,0.51f,0.48f,0.52f,0.50f,
                           0.47f,0.53f,0.49f,0.51f,0.46f,0.52f,0.49f,0.51f,
                           0.48f,0.53f,0.50f,0.47f,0.56f,0.60f,0.63f,0.65f};
  const int expected_plain[] = {1,1,1,1,2,1,2,2,1,2,1,2,1,2,1,2,1,2,2,1,2,2,2,2};
  int selected = -1, plain_changes = 0, held_changes = 0, plain_previous = -1;
  for (int i = 0; i < 24; ++i) {
    const int plain = static_cast<int>(reading[i] * 4.0f);
    const int next = SelectHysteretic(reading[i], 4, selected, 0.2f);
    if (i > 0 && plain != plain_previous) ++plain_changes;
    if (i > 0 && next != selected) ++held_changes;
    plain_previous = plain;
    selected = next;
    CHECK(plain == expected_plain[i] && selected == (i >= 20 ? 2 : 1));
    std::printf("hysteresis,%d,%d,%d\n", i, plain, selected);
  }
  CHECK(plain_changes == 15 && held_changes == 1);

  // Debounce: synthetic 1 ms samples of a contact that bounces for a few
  // milliseconds on press and on release. Counting raw closures gives five
  // presses; a 5 ms stable-state qualification publishes one.
  DebouncedButton button;
  CHECK(button.Configure(5, 5, false));
  const int contact[] = {0,0,0,0,1,0,1,0,1,1,1,1,1,1,1,1,1,1,0,1,0,1,0,0,0,0,0,0,0,0};
  const int expected_raw[] = {0,0,0,0,1,1,2,2,3,3,3,3,3,3,3,3,3,3,3,4,4,5,5,5,5,5,5,5,5,5};
  int raw_presses = 0, presses = 0;
  bool raw_closed = false;
  for (int ms = 0; ms < 30; ++ms) {
    const bool closed = contact[ms] != 0;
    if (closed && !raw_closed) ++raw_presses;
    raw_closed = closed;
    if (button.Observe(closed, static_cast<uint32_t>(ms)) && button.pressed()) ++presses;
    CHECK(button.pressed() == (ms >= 13 && ms < 27));
    CHECK(raw_presses == expected_raw[ms] && presses == (ms >= 13 ? 1 : 0));
    std::printf("debounce,%d,%d,%d\n", ms, raw_presses, presses);
  }
  CHECK(raw_presses == 5 && presses == 1 && !button.pressed());

  // Latest request: six preset requests two ticks apart while each fade takes
  // five ticks. Restarting the fade on every request finishes nothing while
  // requests keep arriving; keeping only the latest request completes the
  // running fade, then starts one fade to the newest preset.
  LatestRequest<int> latest;
  const int kFadeTicks = 5;
  const int expected_started[] = {1, 3, 6};
  int restart_end = -1, restart_done = 0, fade_end = -1, done = 0, started = 0;
  for (int tick = 0; tick < 15; ++tick) {
    if (tick == fade_end) { ++done; fade_end = -1; }
    if (tick == restart_end) { ++restart_done; restart_end = -1; }
    if (tick % 2 == 0 && tick <= 10) {
      const int preset = tick / 2 + 1;
      restart_end = tick + kFadeTicks;
      latest.Request(preset);
    }
    int preset = 0;
    if (fade_end < 0 && latest.Take(preset)) {
      CHECK(started < 3 && preset == expected_started[started]);
      ++started;
      fade_end = tick + kFadeTicks;
    }
    CHECK(restart_done == 0 && done == (tick >= 10 ? 2 : tick >= 5 ? 1 : 0));
    std::printf("transitions,%d,%d,%d\n", tick, restart_done, done);
  }
  CHECK(started == 3 && restart_end == 15 && !latest.pending());
}
