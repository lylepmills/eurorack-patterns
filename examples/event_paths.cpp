// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
// Synthetic single-owner integration. Hardware sampling, output writes, and
// synchronization are deliberately supplied by an integrating application.
#include <eurorack_patterns/pickup.h>
#include <eurorack_patterns/pulses.h>
#include <eurorack_patterns/trigger_delay.h>
#include <eurorack_patterns/transitions.h>
#include <cstdio>

using namespace eurorack_patterns;

// A single-owner, one-slot stand-in for an outbound transport queue.
struct OutboundQueue {
  bool full = false;
  unsigned payload = 0;
  bool TryEnqueue(unsigned value) {
    if (full) return false;
    payload = value; full = true; return true;
  }
};

static bool Publish(LatestRequest<unsigned>& request, OutboundQueue& queue) {
  unsigned value = 0;
  if (!request.Peek(value) || !queue.TryEnqueue(value)) return false;
  return request.Take(value);  // Consumption follows successful enqueue.
}

int main() {
  TriggerDelay<8> delay;
  PulseTimer outputs[2];
  for (auto& output : outputs)
    if (!output.Configure(2, PulseRetriggerPolicy::kRestart)) return 1;

  // Fixed-cadence ticks. Each due input retains its output identity.
  for (uint32_t tick = 0; tick <= 7; ++tick) {
    for (auto& output : outputs) output.Advance(tick);
    if (tick == 0 && !delay.Schedule(1u, 3)) return 1;
    if (tick == 1 && !delay.Schedule(2u, 3)) return 1;
    const uint32_t due = delay.Tick();
    for (unsigned i = 0; i < 2; ++i)
      if (due & (1u << i)) outputs[i].Trigger(tick);
    // A real adapter writes active() to each pin at this service point.
    if (outputs[0].active() != (tick >= 3 && tick < 5)) return 1;
    if (outputs[1].active() != (tick >= 4 && tick < 6)) return 1;
  }

  PickupLatch pickup;
  if (!pickup.Configure(0.2f, 0.8f, 0.01f) || !pickup.Arm(0.9f)) return 1;
  if (pickup.state() != PickupLatch::State::kUnreachable) return 1;
  // The UI explains the mismatch; an explicit target change re-arms pickup.
  if (!pickup.Arm(0.5f) || pickup.Observe(0.2f)) return 1;
  if (!pickup.Observe(0.8f)) return 1;

  // Retryable continuous feedback: inspect pending work before trying enqueue.
  // Queue rejection must NOT consume it. No reentrant requests/concurrent owner
  // may intervene between Peek, successful enqueue, and Take.
  LatestRequest<unsigned> feedback;
  OutboundQueue queue;
  if (!queue.TryEnqueue(1)) return 1;  // Simulate a busy transport.
  feedback.Request(127);
  if (Publish(feedback, queue) || !feedback.pending()) return 1;
  queue.full = false;  // The transport drains its previous item.
  if (!Publish(feedback, queue) || queue.payload != 127) return 1;
  if (feedback.pending() || Publish(feedback, queue)) return 1;
  feedback.Request(127);
  feedback.Request(64);  // Latest-value coalescing is deliberate for this use.
  if (Publish(feedback, queue) || !feedback.pending()) return 1;
  queue.full = false;
  if (!Publish(feedback, queue) || queue.payload != 64 || feedback.pending()) return 1;
  // Use an event queue instead if intermediate notes/edges must survive.
  std::puts("PASS: synthetic delayed outputs, unreachable pickup, feedback retry");
}
