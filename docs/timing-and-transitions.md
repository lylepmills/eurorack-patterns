# Timing and deferred transitions

`DebouncedButton` in [timing.h](../include/eurorack_patterns/timing.h) requires a mechanical contact to remain in its proposed new state for a caller-selected duration. Press and release may use different durations. A contrary or invalid observation restarts the qualification. Startup uses an explicitly supplied logical state; the first different observation begins qualification. Zero duration accepts immediately. Timestamps are unsigned milliseconds: ordinary wrap works, but calls must move forward with intervals shorter than 2^31 milliseconds. The component cannot know about bounce between acquisitions. Poll frequently enough for the contact and application; signal a missed acquisition as invalid.

Use [edge capture](inputs.md) for musical clocks and triggers. A button filter can deliberately reject a pulse that a musical input must retain. There is no universal debounce duration in this library. See [A06](catalog.md#a06-keep-button-debounce-out-of-high-rate-clock-paths).

`LatestRequest<T>` in [transitions.h](../include/eurorack_patterns/transitions.h) stores at most one pending destination. Repeated `Request` calls replace it. `Peek` observes without consuming; `Take` consumes once and leaves its output unchanged when empty. `Cancel` removes pending work and does not cancel a transition already taken by the application. This supports selecting the newest preset after a busy transition, or committing an edit at a musical boundary. The application chooses that boundary and owns the actual audio transition. See catalog F02 and D06.

Use a small trivially copyable, trivially default-constructible and trivially copy-assignable ID or value as `T`. The class does not allocate, but copying the chosen type still costs its size. Pass IDs rather than owning pointers; resource lifetime remains the caller's responsibility. These classes require a single owner or external synchronization. They do not synchronize an interrupt and a foreground thread.

The corresponding host tests cover invalid gaps, timer wrap, zero-duration behavior, repeated events, request bursts and cancellation. These tests establish the state-machine behavior, not a hardware-specific latency or click-free audio guarantee.

## Additional event paths

[`PulseTimer`](pulses.md) handles logical expiry and explicit retrigger policy. [`TriggerDelay`](trigger-delay.md) preserves input identity while waiting a bounded number of caller ticks. Neither replaces acquisition or hardware output service.

For retryable continuous feedback, `Peek` a `LatestRequest`, attempt enqueue, and `Take` only after acceptance. Keep those operations under one non-reentrant owner or external synchronization. The [event-path example](../examples/event_paths.cpp) tests queue rejection and retry. Latest-value replacement deliberately discards intermediates; note events and other multiplicity-sensitive work need an event queue.
