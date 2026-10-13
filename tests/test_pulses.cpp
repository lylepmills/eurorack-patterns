// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include <eurorack_patterns/pulses.h>

#include <cstdint>
#include <cstdio>
#include <cstdlib>

using eurorack_patterns::PulseRetriggerPolicy;
using eurorack_patterns::PulseTimer;

#define CHECK(condition) do { if (!(condition)) { \
  std::fprintf(stderr, "%s:%d: %s\n", __FILE__, __LINE__, #condition); \
  std::exit(1); } } while (0)

// Synthetic 64-bit reference. It stores an absolute deadline rather than
// subtracting modular timestamps, and is only fed monotonically increasing time.
struct ReferencePulse {
  uint64_t deadline;
  uint32_t width;
  PulseRetriggerPolicy policy;
  bool active;
  ReferencePulse(PulseRetriggerPolicy p) : deadline(0), width(1), policy(p),
      active(false) {}
  bool Advance(uint64_t now) {
    if (!active || now < deadline) return false;
    active = false;
    return true;
  }
  bool Trigger(uint64_t now) {
    Advance(now);
    if (width == 0 ||
        (active && policy == PulseRetriggerPolicy::kIgnoreWhileActive))
      return false;
    active = true;
    deadline = now + width;
    return true;
  }
  bool Cancel() {
    bool was_active = active;
    active = false;
    return was_active;
  }
  void Configure(uint32_t next_width, PulseRetriggerPolicy next_policy) {
    width = next_width;
    policy = next_policy;
    active = false;
  }
};

static void BasicContracts() {
  PulseTimer pulse;
  CHECK(!pulse.configured());
  CHECK(!pulse.Trigger(0));
  CHECK(!pulse.Advance(0));
  CHECK(!pulse.Cancel());
  CHECK(!pulse.Configure(0x80000000u, PulseRetriggerPolicy::kRestart));
  CHECK(!pulse.Configure(1, static_cast<PulseRetriggerPolicy>(99)));
  CHECK(pulse.Configure(10, PulseRetriggerPolicy::kRestart));
  CHECK(pulse.Trigger(100));
  CHECK(pulse.active());
  CHECK(pulse.Trigger(105));  // Restart, but output was already active.
  CHECK(!pulse.Advance(110));
  CHECK(!pulse.Advance(114));
  CHECK(pulse.Advance(115));
  CHECK(!pulse.Advance(115));
  CHECK(!pulse.active());

  CHECK(pulse.Trigger(200));
  CHECK(!pulse.Configure(0x80000000u, PulseRetriggerPolicy::kIgnoreWhileActive));
  CHECK(!pulse.Configure(3, static_cast<PulseRetriggerPolicy>(99)));
  CHECK(pulse.active() && pulse.duration() == 10 &&
        pulse.policy() == PulseRetriggerPolicy::kRestart);
  CHECK(pulse.Configure(10, PulseRetriggerPolicy::kIgnoreWhileActive));
  CHECK(!pulse.active());
  CHECK(pulse.Trigger(210));
  CHECK(!pulse.Trigger(215));
  CHECK(pulse.Advance(220));
  CHECK(pulse.Trigger(220));  // Exact expiry is no longer active.
  CHECK(!pulse.Trigger(220));
  CHECK(pulse.Cancel());
  CHECK(!pulse.Cancel());
  CHECK(!pulse.Advance(230));  // Old deadline cannot end a new state.
  CHECK(pulse.Trigger(231));
  CHECK(!pulse.Advance(239));
  CHECK(pulse.Advance(241));  // Late service expires once.

  CHECK(pulse.Trigger(250));
  CHECK(pulse.Cancel());
  CHECK(pulse.Trigger(253));
  CHECK(!pulse.Advance(260));  // Canceled deadline cannot end rearmed pulse.
  CHECK(pulse.Advance(263));

  CHECK(pulse.Configure(0, PulseRetriggerPolicy::kRestart));
  CHECK(!pulse.Trigger(300));
  CHECK(!pulse.active());
  CHECK(!pulse.Advance(301));
  CHECK(pulse.Configure(3, PulseRetriggerPolicy::kRestart));
  CHECK(pulse.Trigger(0xfffffffeu));
  CHECK(!pulse.Advance(0xffffffffu));
  CHECK(!pulse.Advance(0u));
  CHECK(pulse.Advance(1u));
  CHECK(pulse.Trigger(1u));
  CHECK(pulse.Cancel());
  CHECK(!pulse.Advance(4u));

  CHECK(pulse.Configure(0x7fffffffu, PulseRetriggerPolicy::kRestart));
  CHECK(pulse.Trigger(0));
  CHECK(!pulse.Advance(0x7ffffffeu));
  CHECK(pulse.Advance(0x7fffffffu));

  CHECK(pulse.Trigger(0xfffffffeu));
  CHECK(!pulse.Advance(0x7ffffffcu));
  CHECK(pulse.Advance(0x7ffffffdu));  // Maximum width across wrap.

  CHECK(pulse.Configure(3, PulseRetriggerPolicy::kIgnoreWhileActive));
  CHECK(pulse.Trigger(100));
  bool pin = pulse.active();
  CHECK(pin);
  CHECK(pulse.Trigger(110));  // Deadline 103 was never serviced.
  CHECK(pin == pulse.active());  // Accepted request, but NO observed low edge.
  CHECK(!pulse.Advance(112));
  CHECK(pulse.Advance(113));
  pin = pulse.active();
  CHECK(!pin);
}

static void SyntheticReferenceTrace(PulseRetriggerPolicy initial_policy) {
  PulseTimer pulse;
  ReferencePulse model(initial_policy);
  CHECK(pulse.Configure(1, initial_policy));
  uint64_t now = uint64_t(0xffffffffu) - 1000u;
  uint32_t random = 0x6d2b79f5u;
  for (unsigned step = 0; step < 20000; ++step) {
    random = random * 1664525u + 1013904223u;
    now += (random >> 24) % 75u;  // Includes repeated timestamps and wrap.
    const uint32_t tick = static_cast<uint32_t>(now);
    switch ((random >> 16) % 7u) {
      case 0:
      case 1:
        CHECK(pulse.Trigger(tick) == model.Trigger(now));
        break;
      case 2:
      case 3:
      case 4:
        CHECK(pulse.Advance(tick) == model.Advance(now));
        break;
      case 5:
        CHECK(pulse.Cancel() == model.Cancel());
        break;
      default: {
        const uint32_t width = (random >> 8) % 90u;
        const PulseRetriggerPolicy policy = (random & 1u)
            ? PulseRetriggerPolicy::kRestart
            : PulseRetriggerPolicy::kIgnoreWhileActive;
        CHECK(pulse.Configure(width, policy));
        model.Configure(width, policy);
        break;
      }
    }
    CHECK(pulse.active() == model.active);
    CHECK(pulse.duration() == model.width);
    CHECK(pulse.policy() == model.policy);
  }
}

int main() {
  BasicContracts();
  SyntheticReferenceTrace(PulseRetriggerPolicy::kRestart);
  SyntheticReferenceTrace(PulseRetriggerPolicy::kIgnoreWhileActive);
  std::puts("PASS: pulse expiry, retrigger, cancellation, wrap, and synthetic reference traces");
}
