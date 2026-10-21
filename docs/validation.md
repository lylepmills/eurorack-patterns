# Evidence and validation

Use this guide to decide what the library supplies and what your firmware still
needs to establish. The [coverage map](coverage.md) distinguishes the 88 catalog
patterns from the nine implemented component families. Source confidence,
implementation correctness and product qualification are separate claims.

## Evidence levels

| Evidence | What it establishes | What it does not establish |
| --- | --- | --- |
| Pinned source/manual or bug-history observation | A documented behavior or a narrowly identified failure motivates a contract. | Our implementation is correct, or an old report describes a current upstream defect. |
| Synthetic host tests and independent reference models | The component follows its stated contract for the tested traces and boundaries. | ADC freshness, electrical limits, real scheduling or comfortable control feel. |
| Complete measured trace on a named fixture | The recorded adapter, circuit and workload behaved as reported; failures remain explicit. | A different board, broader workload, production circuit or universal tuning constant. |
| Product qualification | The intended hardware and integrated UX meet a product's declared requirements. | This repository does not currently claim production-module qualification. |

The source survey is curated, not exhaustive. See its
[scope and unresolved reports](research-pass-2.md). Inspected upstream tests
were read, not executed. The measured work used one Seed3 control/jack fixture
and a second Seed3 as an independent stimulus generator; that is not validation
on two hardware families. The Pico example was compiled/linked, not measured.

## Reusable lessons from the hardware work

| Contract to carry into an adapter | Evidence and counterexample | Integration obligation |
| --- | --- | --- |
| Treat freshness and validity as part of each sample. | ADC gaps held accepted values; hidden crossings did not grant pickup. A held value alone cannot identify missing acquisition. | Report invalidity before motion filtering; detect duplicate/missing acquisition, and pair a conversion with the probe used for it. |
| Give each shared knob an explicit owner and target. | Bidirectional movement, reversals and target edits reacquired without an early overwrite. | Rearm on external target/owner changes; reset history across gaps; choose effective bounds and UI feedback. |
| Give each press one role and a cancellation policy. | Holds did not also tap on release; interrupted gestures stayed cancelled; selected startup-held cases required a fresh press. | Keep button validity separate from ADC validity, define startup/recovery, and evaluate thresholds at actual service observations. |
| Qualify jack presence separately from signal value and musical gate edges. | Silent/open-ended cables, slow insertion and transition faults exercised the window/streak policy. Correlated input or a prolonged partial insertion can still satisfy a detector. | Generate valid probe evidence, expose unknown/stale state, and choose latency and electrical thresholds for the circuit. |
| Budget the longest interruption, not only CPU utilization. | Six jack-load profiles starved qualification while audio deadlines passed. Bounded acquisition phases restored responsiveness in all 21 reruns. | Establish acquisition ownership/deadlines and measure both audio and control paths; do not copy one board's interrupt priorities as a universal fix. [B07](catalog.md#b07-let-a-timer-and-dma-own-the-acquisition-frame) records the hardware-timed alternative: a timer-triggered, DMA-chained scan with one interrupt per frame. |
| Validate the recorder as well as the firmware. | Loose probes, missing capture tails and extra receiver edges caused real rejections. | Require complete coverage and independent stimulus; retain failed runs and do not filter them into passes. |

Holding a published value or presence state is a defined recovery behavior, not
proof that it is still current. An application may need a stale-state indication
or a timeout policy. The library does not choose that musical decision.

## Measured scope and remaining limits

| Area | Recorded evidence | Still outside the claim |
| --- | --- | --- |
| Pickup, motion and gestures | [Initial and fault/startup recordings](bench/daisy.md#first-daisy-measurements), moving targets, bidirectional hidden crossings, taps/holds during motion and fast reversals under the stated load. | Every mapping, control feel, every reset phase, brownout recovery, multiplexed ADC behavior or other boards. |
| Button timing and recovery | [22 accepted threshold/fault cases](bench/daisy.md#configurable-receiver-fault-timing), plus fixed-delay comparisons; original failed attempts retained. | Exhaustive service-phase coverage, arbitrary contact bounce, universal debounce/hold durations. |
| Jack presence | [Physical jack records](bench/daisy.md#recorded-jack-transition-and-motion-evidence): ordinary/slow movement, passive silent source, two open-ended cables, four manual transition faults; 110 automated electrical cases including baselines. | Electrical clamp stimulus is not mechanical insertion. Powered Eurorack voltages, all sockets/cables, correlated sources and mechanical seating time remain unqualified. |
| Acquisition under interrupt load | [21 scheduled-acquisition comparisons](bench/daisy.md#scheduled-jack-acquisition-results) and two stop/drain checks; all previously starved profiles became responsive. | Arbitrary IRQ masking, interrupt priorities, display/storage/USB combinations or production audio quality. |
| Real DSP/DMA and clock observations | [Archived fixture investigation](investigations/daisy-clock.md): matched-work diagnostics separate counted-clock scheduling from external stability; failed results preserved. | External clock failures remain unresolved. No absolute calibration, oscillator diagnosis, audio-fidelity qualification or portable memory-placement rule. |
| Event counts, physical pulses, trigger delay and deferred changes | Host contracts and adversarial reference tests; runnable compositions. | Minimum physical pulse widths, delivery jitter, receiver compatibility, CV/gate skew, queue synchronization and safe audio transition boundaries. |
| Storage, protection and recovery recipes | Attributed catalog observations and proposed checks. | Power-cut atomicity, brownout behavior, hot-patching survival or production electrical certification. |

These counts describe distinct campaigns and accepted captures, not a single
exhaustive qualification suite. A regression that expects a historical failure
passes by detecting that failure; it does not promote the recording to a
hardware pass. Numerical tolerances, windows, filters and resistor values belong
to their recorded setup and are not recommended defaults for a new module.

## What changed, and where

The nine portable headers are unchanged from v0.2.0 through this consolidation.
Version 0.2.1 added integration guidance, examples and host checks; that release
predates the hardware measurements. Later work added measured regression data
and repaired the Seed3 adapter's acquisition scheduling, stop/drain ownership,
and capture integrity. Those are useful reference implementations with
board-specific dependencies. They do not add a new portable scheduling API.

The source-history pass supplied `PickupLatch`, `PulseTimer` and `TriggerDelay`;
their source provenance is distinct from later bench evidence. See the
[changelog](../CHANGELOG.md) and [attribution](../ATTRIBUTION.md).

## Executed host checks

The default build exercises portable contracts. Board-adapter simulations and
measured replays are separate opt-in configurations; see [test boundaries and
evidence downloads](evidence.md). Downloaded traces retain their original hashes,
and missing or changed data fails configuration rather than skipping a test.

The suite combines synthetic adversarial fixtures with the explicitly labeled [Daisy measurements](bench/daisy.md#first-daisy-measurements). The published 0.2.1 release predates those measurements. The CMake tests use always-active checks in release builds, compile as C++11 with warnings as errors and no exceptions/RTTI, compile every public header independently, and exercise an installed-package consumer. The existing CI matrix covers Linux, macOS and Windows; Linux enables address and undefined-behavior sanitizers. The second pass also ran the local suite with those sanitizers on Apple Clang.

| Mechanism | Evidence executed in this repository | What the check cannot establish |
| --- | --- | --- |
| Presence qualification | Startup/chatter/gap traces; all 6,561 eight-symbol traces over match/mismatch/invalid for 30 small window/threshold/streak configurations. Invalid-gap restart equivalence and published-state preservation. | Probe generation, correlated audio rejection, jack contacts, actual insertion latency. |
| Edge capture | Threshold/acquisition/overflow traces; deterministic independent three-level reference plus event-count conservation under bounded queues and invalid samples. | Pulses missed by acquisition, electrical thresholds, concurrent access safety. |
| Existing control helpers | Endpoint, slow-motion and pickup checks; transfer-map order/range/symmetry and selector sweeps. | ADC noise, comfortable neutral widths, musician preference. |
| Mechanical debounce | Bounce/invalid traces; unwrapped 64-bit reference time versus modular timestamps; directed maximum-duration and wrap/gap boundaries. | Unobserved contact bounce or an appropriate physical debounce time. |
| `PickupLatch` | Unreachable/reversed/constant ranges, strict tolerance, skipped targets, rearm, invalid-gap history break, rejected configuration and bidirectional sweeps. | Discrete/nonmonotone reachability, external target changes the caller fails to report. |
| [Five-step application example](pickup.md#one-stepped-destination-policy) | Independent finite-set oracle over 7,776 synthetic sequences; both sweep directions, coarse skips, midpoint boundaries, explicit rearm, invalid gaps, unreachable recovery and destination readback. | Other quantizers, asynchronous writes, unreported external edits, physical boundary noise or control feel. |
| `PulseTimer` | Exact expiry, maximum width/wrap, ignored/restarted requests, zero disable, cancel/rearm and stale deadline; two 20,000-step absolute-deadline reference traces. An unserviced expiry/retrigger explicitly produces no observed low edge. | Physical width, edge jitter, separate retrigger delivery, polarity, hardware timer dispatch. |
| `TriggerDelay` | A/B identity regression, overlapping deadlines, zero/maximum/invalid delay, high bit, reset, coalescence, ring wrap; 2,000 ticks compared to an absolute-deadline map; C++11 public-constant linkage. | Sub-tick multiplicity, fixed real-time cadence, CV settling, electrical inputs. |
| Integration compositions | Runnable control and event-path examples, including delayed per-output pulses, pickup reachability and retaining feedback after queue rejection. | A complete firmware adapter or timing on a real interrupt/foreground boundary. |

Independent review corrected test blind spots before release: the event reference initially reused the class under test, and random timing inputs never exercised acceptance at the maximum duration. Review also found and fixed a C++11 link failure when taking the address of the trigger delay's public constants. These are host-level findings, not upstream module bugs.

## How to promote a pattern

1. Pin the source or failing observation and inspect its context. Distinguish a
   merged fix, branch proposal, user report and measured result.
2. Specify units, ownership, startup, invalidity, bounds, cancellation and order.
   Include a counterexample to an overly broad recommendation.
3. Build a small adversarial replay, with an independent oracle where practical.
   Exercise exact boundaries, reset/rearm, missing data and time wrap.
4. Measure the adapter on its actual circuit and schedule. Buffer instrumentation
   outside timing-critical work and establish complete physical coverage.
5. Validate musical behavior with intended receivers, real patching and users.
   Record latency, false/lost actions, recovery and control feel against a stated
   requirement. A second hardware family adds stronger portability evidence than
   another wrapper around the same SDK.

## Next measurements, in useful order

The Daisy investigation is closed; further clock diagnosis is not a prerequisite
for using or extending these components. New experiments should start with a
named reusable contract or product decision, a finite case list, an acceptance
budget, and a stopping rule. Expand the scope only when a failure changes that
decision. Unexplained fixture anomalies can remain documented open questions.

| Candidate | Decision it can inform | Bounded starting point |
| --- | --- | --- |
| Second hardware family | Does the sample/time/ownership boundary transfer? | Replay selected validity, pickup, gesture and presence cases through one unrelated adapter. |
| Physical output pulses | Does the receiver see the requested events under load? | Measure high/low widths and delivery jitter across restart, cancel and late service. |
| CV-before-gate acquisition | Which acquisition/latency policy preserves the intended note? | Sweep positive/negative CV-to-gate skew against a declared note-rate and latency budget. |
| Integrated control feel | Are technically correct takeover and gestures understandable? | Try endpoints, slow/fast movement, mode changes and target edits with real users. |
| Persistence, when implemented | Can interrupted writes recover a coherent supported state? | A separate controlled power-cut campaign against the actual storage backend. |

## Trace provenance

Record board revision, firmware commit, acquisition date/method, units/scaling,
sample timestamps, calibration limits, missed/duplicate indicators, achieved
workload and independent stimulus or ground truth. State the expected result
and why it is independent of the algorithm under test. Separate generated
stimuli from physical contacts and measured samples from synthetic fixtures.
Remove device identifiers, personal information and private patches.

Retain original acquisitions and a minimal replay with a documented
transformation. A replay tests behavior; independent physical capture tests the
adapter. Neither substitutes for the other. Short windows, selected samples,
aggregate soaks and full recordings must keep their different coverage labels.

## Detailed records

- [Daisy procedures and measured cases](bench/daisy.md): historical firmware,
  wiring, commands, accepted results and retained rejections.
- [Closed clock investigation](investigations/daisy-clock.md): full diagnostic
  chronology, unresolved physical cause and native-evidence limits.
- [Shared-knob integration](quickstart.md) and [Pico adapter](../examples/pico/README.md):
  application boundaries and compiler checks. The Pico has not been measured.

<!-- Compatibility anchors for the former long-form validation guide. -->
<a id="daisy-seed3-jack-presence-bench"></a>
<a id="jack-audiointerrupt-load-results"></a>
<a id="scheduled-jack-acquisition-results"></a>
<a id="recorded-jack-transition-and-motion-evidence"></a>
<a id="daisy-seed3-control-bench"></a>
<a id="first-daisy-measurements"></a>
<a id="active-fault-and-startup-measurements"></a>
<a id="fixture-and-saleae-connections"></a>
<a id="build-without-accessing-hardware"></a>
<a id="capture-and-replay"></a>
<a id="automatic-startup-recording"></a>
<a id="audiousb-load-and-continuous-soak"></a>
<a id="transfer-integrity"></a>
<a id="first-measurements-and-acceptance"></a>
<a id="independent-button-stimulus-apparatus"></a>
<a id="automated-two-board-button-cases-2026-10-18"></a>
<a id="configurable-receiver-fault-timing"></a>

These historical sections moved to the [Daisy bench record](bench/daisy.md).

<a id="jack-dsp-and-memory-dma-campaign-partial-hardware-results"></a>
<a id="internal-ram-versus-sdram-measured-comparison"></a>
<a id="controlled-firmware-comparison-current-previous-current"></a>
<a id="fixed-sdram-buffer-placement-in-one-image"></a>
<a id="fixed-storage-buffer-alignment-comparison"></a>

These historical sections moved to the [clock investigation archive](investigations/daisy-clock.md).

<a id="integration-preparation-in-021"></a>
The 0.2.1 preparation is described in the [release history](../CHANGELOG.md#021--2026-10-13).
