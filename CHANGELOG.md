# Changelog

## Unreleased — on `main` after 0.2.1, not yet tagged

Everything in this section is documentation, example, test and bench work. The
nine public headers are unchanged since 0.2.0, and no release carries these
changes yet; pin a tagged release, not `main`.

- Move the Daisy bench's host tests and measured reports from `tests/` to
  `bench/daisy/tests/` and `bench/daisy/measured/`, so `tests/` holds only the
  library's own tests. The evidence downloader installs the unchanged, immutable
  release archives (whose members keep the `tests/measured/` prefix) under the
  new directory; no library, test or report content changes.
- Add B07, hardware-timed acquisition (a timer-triggered, DMA-chained pot scan
  inspected in Beads), and cross-link it from A01 and the validation guide.
  Add labelled counterexamples and proposed tradeoffs to A05, B04, C05, C06,
  C09, E02 and H01; the catalog now lists 89 patterns.
- Add a five-step pickup application example with explicit membership, snapping,
  destination readback and unreachable-target recovery. Check its policy with
  an independent finite-set oracle and synthetic boundary/ownership cases;
  the public API is unchanged and no control-feel measurement is claimed.
- Keep default tests focused on portable contracts. Make board simulations and
  measured replays explicit options; require verified evidence before replay.
- Distribute large recordings as optional release assets with archive/member
  SHA-256 checks. Keep reports in Git and preserve exact measured source
  revisions in a separate history bundle. Add a code map for the optional bench.

- Consolidate [reusable lessons and validation limits](docs/validation.md).
  Separate the detailed [Daisy bench record](docs/bench/daisy.md) and
  [closed clock investigation](docs/investigations/daisy-clock.md) from the
  library's integration guide. Preserve all measured traces and failed cases.
- Add a Seed3 reference adapter with fresh ADC evidence, explicit startup/gap
  policies, independent stimulus and buffered capture/replay. Retain attribution
  for the adapted libDaisy Seed3 SAI configuration.
- Add measured pickup, gesture, startup, simultaneous-control and fault cases,
  physical jack insertion/removal records and a 110-case electrical fault matrix.
  These are bounded fixture results, not production electrical qualification.
- Fix jack-acquisition starvation in the Seed3 adapter with bounded timer/ADC
  phases and explicit ownership; all 21 load/recovery/fault reruns pass, including
  the six previously starved profiles. Two early-finish checks cover the corrected
  stop/drain deadline. Audio and acquisition acceptance remain separate.
- Harden capture completion, transport integrity, physical coverage and receiver
  review. Preserve incomplete recordings, receiver glitches and timing failures
  as explicit regressions; do not widen limits to make them pass.
- Preserve real DSP/DMA and clock diagnostics, including matched buffer-placement
  and analog probe-path comparisons. The clock investigation is closed with its
  physical cause unresolved; no oscillator, codec-quality or portable memory-
  placement conclusion follows. Detailed methods/results remain in the archive.
- The nine portable headers and their interfaces remain unchanged from v0.2.0.

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
