<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright 2026 Lyle Mills -->

# Presence and event input contracts

These C++11 headers contain one-channel state machines. They allocate no memory,
throw no exceptions, and depend only on the standard C++ library. They do not
read ADCs, generate a normalization probe, schedule scans, or synchronize
threads/interrupts. Configure returns `false` for invalid parameters and leaves
the existing state untouched. Callers should check its return value.

## Presence evidence

`PresenceDetector` receives one `PresenceEvidence` for each **fresh, correctly
paired** probe/input observation. `kMatch` means the input followed the probe;
`kMismatch` means it did not; `kInvalid` means that observation cannot be
trusted. In this convention, sustained mismatches suggest a patched jack.
Exactly how raw voltage and probe polarity become match/mismatch belongs to the
carrier adapter. A silent connected source still produces mismatches if it does
not follow the probe. A correlated external source can mimic the probe, so this
method does not prove physical cable presence in every circuit.

`PresenceConfig` requires nonzero `window_size`, `mismatch_threshold` in
`[1, window_size]`, and nonzero `bad_windows_required`. A full window is bad
when its mismatch count is **at least** `mismatch_threshold`. One good window
publishes unpatched and clears the bad-window streak. A patched transition
after startup requires `bad_windows_required` consecutive bad windows. These
are *observation counts*, not milliseconds; the caller must document the
acquisition cadence and choose counts after measuring its circuit. No count in
this library is a universal electrical threshold or time constant.

`PresenceStartup{known, patched}` controls the initially published state.
`ready()` is true immediately when `known` is true; otherwise it becomes true
when a complete valid window can publish a state. `patched()` alone is not a
valid answer while `ready()` is false. With `kFirstWindowDecides`, the **first
complete valid window** publishes patched or unpatched immediately, even if a
known initial state was provided. After that first decision, normal consecutive-bad-window rules apply. With
`kRequireStreak`, an unknown startup remains unready through bad windows until
the required streak completes; the first good window can publish unpatched.
An initially known state remains published during that acquisition period.

`kInvalid` discards the partial window and consecutive bad-window streak. It
holds the last published `ready()`/`patched()` result. It does not add evidence,
advance a window, or reinterpret a stale input value. `observations()` and
`mismatches()` expose the current partial window; `windows()` counts completed
valid windows (saturating at `UINT32_MAX`); `last_mismatches()` retains the last
completed window even across invalid gaps. `bad_windows()` is capped at the
configured requirement.

For a scan adapter, keep the probe bit **used during acquisition** with the
sample. Validate the per-channel conversion word before using its numeric
value. An adapter may retain a previous value after a bad conversion, so a
frame-wide error total alone cannot safely identify which channels have fresh evidence. A duplicate frame must not count again;
mark it invalid. On a detected missing frame, issue `kInvalid` before scoring
the next fresh frame to break continuity. Detect missing/duplicate frames
using an acquisition/source sequence that actually identifies scan instances;
a sequence that increments only when decoding is called cannot, by itself,
prove that an upstream acquisition was lost.
The portable detector has no sequence counter because transports differ.

Budget the longest interruption of acquisition, not only average CPU use. In
the [Daisy load campaign](bench/daisy.md#jack-audiointerrupt-load-results), 25%
padding in 16-sample audio callbacks preserved every 500 us observation slot;
the same nominal percentage in 96-sample callbacks prevented qualification.
The longer uninterrupted callback exceeded the foreground acquisition budget.
Invalidating those observations prevented false progress, but could not make
the detector responsive. All three heavy-load recovery tests recognized a
sustained insertion after the load stopped. Measure consecutive valid
observations and recovery as well as audio deadlines. A faster acquisition
path, DMA, or different scheduling needs its own evidence; accepting late or
duplicated samples to hide starvation would break this contract.
Holding the published state is not a freshness guarantee: it can become stale
while the cable changes. The host can monitor time since a completed valid
window and choose an explicit stale-state indication or routing policy.

The synthetic presence fixtures cover startup invalid data, a first-window
decision, partial insertion chatter, unplug/reinsert, sustained bad windows,
and adapter-labeled missing/duplicate observations. They do not claim
hardware-tested behavior. The decision pattern was informed by [Mutable
Instruments Beads normalization detection at revision
`f4cfa7697095a28d292bff758beb51deb49b5a86`](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/normalization_detector.cc),
as recorded in the [catalog](catalog.md). This header is an
independent implementation of the stated behavior, with explicit validity and
startup configuration; no Beads source text was copied.

## Rising edge capture

`RisingEdgeCapture<Sample>` accepts arithmetic sample types. Configure with a
low threshold strictly below the high threshold, a nonzero maximum pending
event count, and `HighAcquisitionPolicy`. The units and electrical scaling are
the caller's. On a known low state, a sample **at or above** high creates one
rising event and enters high; on a known high state, a sample **at or below**
low rearms low. Values between thresholds retain the known state. On first
acquisition or reacquisition after a gap, a middle value leaves the level
unknown. An acquired high either seeds the high state silently or counts one
rise, according to `kSeedSilently` or `kCountAsRise`. The same explicit policy
applies at startup and after invalid gaps.

An invalid acquisition (`valid == false`, NaN, or either infinity for a
floating sample) clears level knowledge while retaining pending events. The
next valid sample must reacquire a threshold state. This avoids inferring an
edge from a stale level across a gap. A real edge that occurred in that gap
cannot be reconstructed. `Observe` returns true only when it enqueued an event.

`pending()` is a bounded **count**, so several acquired low/high pulses can
survive a slower consumer. `Consume(maximum)` removes at most that many events;
zero is a no-op. At capacity, new events are dropped and `overflowed()` latches
true. `Consume` does not clear overflow; use `ClearOverflow()` after the owner
has handled the loss indication. Overflow says that at least one event was
lost; it does not report how many. `Reset()` clears level knowledge, pending
events, and overflow while retaining the configuration. Thresholds must be
finite. The component has no timing/debounce/refractory policy, timestamps, or
event order between multiple channels.

Sample at a rate that can observe the pulses of interest. A pulse entirely
between two acquisitions is invisible to this class; an ISR, comparator, or
faster acquisition path is required for that case. It also cannot recover
multiple pulses contained in one sample interval. The producer and consumer
must share one owner or use caller-provided synchronization: these methods are
not atomic or interrupt-safe merely because the counter is bounded.

The synthetic event fixtures exercise slow/noisy threshold crossings,
multiple observed pulses before a slower consume, saturation, overflow
latching, startup high, and invalid gaps. The tests compile the trace data
into the executable, so they run from any working directory. They are
host-level contracts, not measurements on Eurorack hardware.
