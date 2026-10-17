# Changelog

## Unreleased

- Preserve a passing continuous 30-minute diagnostic soak: 1.8 million physical
  service pulses, unchanged timing limits and selected raw-timer comparisons.
  The earlier late-run disagreement did not recur and remains unresolved.
- Retain four measured short timing comparisons with diagnostics off/on and
  audio/USB load off/on. Explicit diagnostic export preserves complete wire data
  and the physical pulses for retained observations and their predecessors;
  selected evidence never claims full-sample replay or resolves an older failure.
- Add optional Daisy timing diagnostics with raw tick/GPIO-call brackets,
  retained maximum-event predecessors and measured retention cost. Host checks
  cover wrap, long elapsed time, wire integrity and same-pulse scope comparison;
  short paired comparisons and one long stationary run now have measured evidence.
- Add optional Seed3 audio-DMA/USB load experiments and a continuous
  aggregate soak recorder (up to one hour), with strict capture checks and a
  stationary campaign runner.
- Retain attribution for the adapted libDaisy Seed3 SAI configuration.
- Preserve three complete paired stationary load traces (30,000 observations)
  with explicit audio/USB workload, host pacing and scope timing evidence.
  Check long-soak pulse counts and per-second extrema independently; aggregate
  evidence never claims individual-sample replay.
- Retain a measured 96-frame scheduling counterexample (1,593 skipped control
  slots despite audio callbacks meeting their period) and an unqualified
  30-minute soak with nine local scope-timing disagreements. Regression tests
  must continue rejecting these failures; no acceptance bounds were widened.

- Allow Daisy recordings up to 150 seconds so operator-led tests can tolerate
  delayed starts. Preserve the full waiting window, check device capacity before
  requesting a run, and retain support for the original 30-second images/traces.
- Add an optional Daisy Seed3 control bench with explicit ADC freshness, a
  100k-pot acquisition configuration, buffered USB traces and Saleae markers.
- Add pickup/gesture/gap/load scenarios, strict capture integrity checks and C++
  trace replay, with synthetic adapter and mocked-serial regressions.
- Preserve six complete first-pass Daisy recordings with allowlisted provenance,
  scope-derived digital edges and measured replay regressions. Keep conclusions
  bounded to one fixture and exclude incomplete or suspect-contact runs.
- Add event-triggered gesture/pickup fault scenarios and a retained 20-second
  automatic startup recorder. Protocol 2 reports/checks stimulus timing and refuses
  to overwrite unread startup evidence.
- Add nine complete measured fault/startup traces (609,923 observations): gesture
  interruption, independent ADC gaps, bidirectional missing-crossing pickup,
  moving targets, released RESET and held-button USB power-on. Include derived
  analog medians, explicit pre-application electrical levels and regression checks.
- Reject missing/glitched service pulses during scope alignment; distinguish
  the observed long pre-application marker level from the complete startup window.
  Keep untriggered and disconnected-probe runs out of published passes.
- Cross-build the Daisy adapter in CI; public core interfaces and behavior are unchanged.

## 0.2.1 — 2026-10-13

- Add a complete pickup integration walkthrough and host-tested application adapter, with invalid samples handled before motion filtering, explicit rearming and reset.
- Add three synthetic before/after illustrations generated from executable-checked traces.
- Add Cortex-M0+ compilation of all headers and an optional Raspberry Pi Pico SDK adapter link build. Neither is a hardware execution or measurement claim.
- Add contributor issue forms, public-path/local-link checks and an immutable-release checklist.
- Preserve all public headers byte-for-byte from 0.2.0; this is an integration, documentation and validation release.

## 0.2.0 — 2026-10-13

- Extend the catalog from 66 to 88 patterns through source and bug-history research into Ornament & Crime, monome Ansible/Teletype and 4ms MetaModule. Strengthen six existing entries and record counterexamples, research bounds, unresolved reports and unmerged branch evidence.
- Add original MIT `PickupLatch`, `PulseTimer` and `TriggerDelay` components with explicit bounds, ownership, invalid/cancel behavior and coalescence limits. Existing 0.1 interfaces retain their behavior.
- Add deterministic independent reference tests, exhaustive small presence traces, directed timer boundaries, standalone C++11 linkage checks and an event-path example including feedback retry after queue rejection.
- Expand provenance and a practical hardware-evidence plan. Host validation remains synthetic; no hardware measurements or upstream firmware test runs are claimed.
- Package version is 0.2.0. CMake's existing `SameMinorVersion` compatibility policy means installed-package consumers requesting 0.1 must explicitly request 0.2 when opting into this release.

## 0.1.0 — 2026-10-13

- Publish an attributed catalog of 66 micro-patterns across jack detection, controls, timing, runtime behavior, recovery, and electrical design.
- Add portable presence qualification, event capture, pickup and control helpers, gesture ownership, mechanical debounce, and deferred latest-request handling.
- Add synthetic adverse-input traces, always-active host tests, standalone header checks, and a runnable example.
- Provide CMake dependency and install targets. Hardware tuning and qualification remain with each integrating product.
