# Evidence and validation

Source confidence and product qualification are different. A verified fix can motivate a good contract; a host test can establish that our implementation follows it; neither proves that a chosen threshold, scan cadence or electrical interface works on a particular module.

## Executed host checks

All fixtures in this release are **synthetic**. No measured hardware trace is included. The CMake tests use always-active checks in release builds, compile as C++11 with warnings as errors and no exceptions/RTTI, compile every public header independently, and exercise an installed-package consumer. The existing CI matrix covers Linux, macOS and Windows; Linux enables address and undefined-behavior sanitizers. The second pass also ran the local suite with those sanitizers on Apple Clang.

| Mechanism | Evidence executed in this repository | What the check cannot establish |
| --- | --- | --- |
| Presence qualification | Startup/chatter/gap traces; all 6,561 eight-symbol traces over match/mismatch/invalid for 30 small window/threshold/streak configurations. Invalid-gap restart equivalence and published-state preservation. | Probe generation, correlated audio rejection, jack contacts, actual insertion latency. |
| Edge capture | Threshold/acquisition/overflow traces; deterministic independent three-level reference plus event-count conservation under bounded queues and invalid samples. | Pulses missed by acquisition, electrical thresholds, concurrent access safety. |
| Existing control helpers | Endpoint, slow-motion and pickup checks; transfer-map order/range/symmetry and selector sweeps. | ADC noise, comfortable neutral widths, musician preference. |
| Mechanical debounce | Bounce/invalid traces; unwrapped 64-bit reference time versus modular timestamps; directed maximum-duration and wrap/gap boundaries. | Unobserved contact bounce or an appropriate physical debounce time. |
| `PickupLatch` | Unreachable/reversed/constant ranges, strict tolerance, skipped targets, rearm, invalid-gap history break, rejected configuration and bidirectional sweeps. | Discrete/nonmonotone reachability, external target changes the caller fails to report. |
| `PulseTimer` | Exact expiry, maximum width/wrap, ignored/restarted requests, zero disable, cancel/rearm and stale deadline; two 20,000-step absolute-deadline reference traces. An unserviced expiry/retrigger explicitly produces no observed low edge. | Physical width, edge jitter, separate retrigger delivery, polarity, hardware timer dispatch. |
| `TriggerDelay` | A/B identity regression, overlapping deadlines, zero/maximum/invalid delay, high bit, reset, coalescence, ring wrap; 2,000 ticks compared to an absolute-deadline map; C++11 public-constant linkage. | Sub-tick multiplicity, fixed real-time cadence, CV settling, electrical inputs. |
| Integration compositions | Runnable control and event-path examples, including delayed per-output pulses, pickup reachability and retaining feedback after queue rejection. | A complete firmware adapter or timing on a real interrupt/foreground boundary. |

Independent review corrected test blind spots before release: the event reference initially reused the class under test, and random timing inputs never exercised acceptance at the maximum duration. Review also found and fixed a C++11 link failure when taking the address of the trigger delay's public constants. These are host-level findings, not upstream module bugs.

## How to promote a pattern

1. **Pin the observation.** Record product, source revision or manual version, exact behavior and whether it is a merged fix, branch proposal, user report or measured result. Read the patch and its callers; avoid inferring a current defect from an old issue title.
2. **Specify the boundary.** State units, ownership, initialization, invalid-data behavior, bounds/overflow, cancellation and ordering. Include a counterexample to an overly broad version of the advice.
3. **Build a small adversarial replay.** Include the reported failure shape, exact boundaries, reset/rearm, gaps, nonfinite inputs where applicable and time wrap. Use an independent representation for an oracle where practical. A test that copies the implementation formula has limited independence.
4. **Measure the adapter.** Establish sample freshness, scan/service cadence, clock domain crossings and worst-case load on the intended board. Instrumentation must not introduce the fault it measures; buffer traces and drain them outside timing-critical work.
5. **Validate product behavior.** Use receiving modules, real patching and musicians. Record false actions, lost events, latency distribution, recovery and control feel against stated acceptance criteria. A second unrelated hardware adapter tests portability better than another wrapper around the same board SDK.

## Next measurements, in useful order

| Experiment | Capture | Acceptance question |
| --- | --- | --- |
| Jack insertion and removal | Raw probe/sample, freshness/sequence, expected probe, qualified state, independent physical/electrical ground truth | Does tentative insertion cause unwanted routing changes? How long do genuine changes take? Repeat silent sources, slow insertion, worn sockets and separately powered cases. |
| Output pulse under load | Requested event time, logical deadline, actual pin high/low edges; stress display, storage and communications | Are minimum high/low widths and worst-case jitter acceptable to the receiver? Can late service join pulses? |
| CV-before-gate acquisition | Independent CV step and gate timing, ADC sample timing, captured value and emitted trigger | What delay preserves intended pitch without losing fast notes? Sweep positive and negative skew. |
| Shared-control takeover | Raw/mapped knob, target, validity, owner/bank changes and resulting value | Is pickup reliable across noise, slow/coarse movement, endpoints, invalid gaps and external edits? Do unreachable indications help the player recover? |
| Saves and teardown | Interrupt/worker timelines, command acceptance, saved bytes, load result, resource lifetime | Are writes coherent and readers quiescent? A separate controlled power-cut campaign is required for atomicity claims. |

Do not set universal numeric thresholds from these host fixtures. Hardware tests should specify an acceptance budget before tuning and keep failing traces as regression inputs afterward.

## Trace provenance

When contributing a measured trace, include device/board revision, firmware commit, acquisition date and method, raw units/scaling, sample period or timestamps, calibration, dropped/duplicate-sample indicators, workload and trigger/ground-truth method. Record the expected result and why it is independent of the algorithm under test. Label generated stimuli separately from recorded samples. Remove device serial numbers, personal data and private patches.

Keep both the original acquisition and a minimal replay, with a documented transformation between them. A replay can validate the pure component while a scope/logic-analyzer capture validates the adapter. Neither should silently stand in for the other.
