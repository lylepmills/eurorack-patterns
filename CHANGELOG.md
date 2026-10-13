# Changelog

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
