# Eurorack patterns

[![Checks](https://github.com/lylepmills/eurorack-patterns/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/lylepmills/eurorack-patterns/actions/workflows/ci.yml)

Small, reusable building blocks for predictable Eurorack controls and firmware, with an attributed catalog of design ideas from existing instruments. A cable should not change routing repeatedly while being inserted. A slow knob movement should eventually register. A modifier gesture should not also fire an unrelated release action. This project collects those details and provides portable implementations where the behavior can be specified and tested independently of a particular module.

The library is `include/eurorack_patterns/`: nine header-only C++11 components. The Daisy bench (`examples/daisy/`, the `test_daisy_*` files and `tests/measured/`) is optional measurement apparatus, not part of the library.

## Three bugs the components prevent

Each picture is generated from an executable-checked **synthetic** sequence in the [trace program](examples/behavior_traces.cpp), not a hardware recording. Counts, thresholds and delays are illustrative; see the [validation limits](docs/validation.md).

**Routing flips while a cable is still going in.** `presence.h` qualifies presence over complete evidence windows, so individual probe mismatches do not change routing.

![Individual probe mismatch toggles during insertion; qualified presence changes after two complete bad windows.](docs/images/presence.svg)

**A recalled value jumps as soon as the knob moves.** `pickup.h` holds the stored value until the knob crosses it.

![Direct knob assignment jumps to 80 percent; pickup holds the stored 30 percent until the knob crosses it.](docs/images/pickup.svg)

**A modifier edit also fires the button's release action.** `gestures.h` gives each press one role; consuming the gesture suppresses its release.

![A modifier edit followed by release causes two naive actions; consuming the gesture leaves one action.](docs/images/gesture.svg)

## Pick your path

- **Designing a module:** browse the [89-pattern catalog](docs/catalog.md) by problem. Each entry names its evidence (code, manual, maker account, release notes or datasheet), cites a pinned source, and proposes a check; the [source and bug-history pass](docs/research-pass-2.md) records the research scope and unresolved reports.
- **Writing firmware:** follow the [shared-knob walkthrough](docs/quickstart.md), start from the example below, then see the optional [Raspberry Pi Pico adapter](examples/pico/README.md).
- **Evaluating the claims:** read the [validation guide](docs/validation.md) for evidence levels, the reusable integration lessons and what remains outside the claim, and the [coverage map](docs/coverage.md) for which patterns have code. Freshness, ownership, recovery and acquisition deadlines belong in every adapter.
- **Contributing:** report a [bug, source correction or measured trace](https://github.com/lylepmills/eurorack-patterns/issues/new/choose) or pick a [bounded contribution task](https://github.com/lylepmills/eurorack-patterns/issues?q=is%3Aissue%20is%3Aopen%20label%3A%22help%20wanted%22); [CONTRIBUTING.md](CONTRIBUTING.md) states the public scope and evidence rules. Sources are credited beside each observation and in [ATTRIBUTION.md](ATTRIBUTION.md).

**Vocabulary.** A *pattern* is one catalog entry: an observed behavior, its source and a proposed check. A *primitive* is a portable operation for that entry in a header; a *recipe* is a documented design choice with no library code; *measure* marks a claim that depends on a circuit, firmware schedule, UI, storage backend or hardware test. *Synthetic* fixtures are generated or simulated; *measured* traces were recorded on a named device, firmware and date.

## Example: one shared knob

For a knob whose parameter can also be changed by a preset or another owner, start with the stateful `PickupLatch`:

```cpp
#include <eurorack_patterns/pickup.h>

eurorack_patterns::PickupLatch pickup;
// Initialization (check Configure/Arm results when using runtime values):
pickup.Configure(0.0f, 1.0f, 0.005f);
pickup.Arm(0.3f); // stored value changed; re-arm on each external edit

// In your single-owner acquisition loop. Without the latch this would be
// set_parameter(mapped_knob_sample) on every sample, and the stored 0.3
// would jump to wherever the knob happens to sit.
if (pickup.Observe(mapped_knob_sample, sample_valid)) {
  set_parameter(mapped_knob_sample);
}
```

`Observe` returns permission to apply a sample, not a changed-value event. The [complete example](examples/pickup_workflow.cpp) adds initialization, validity before motion filtering, ownership changes and reset; the walkthrough explains the ordering and policies. For a discrete destination, the [five-step pickup example](docs/pickup.md#one-stepped-destination-policy) checks actual membership and destination readback, with explicit recovery for an unreachable saved value. The [control-loop](examples/control_loop.cpp) and [event-path](examples/event_paths.cpp) examples compose the other components, including retry after queue rejection.

`controls.h`'s lower-level predicates and percent convenience functions remain supported for applications that already manage pickup state and history; they do not automatically break crossing history across invalid gaps. Numeric tolerances are configurable demonstration values.

## Included components

| Header | Reusable behavior | Contract and examples |
| --- | --- | --- |
| `presence.h` | Evidence windows, asymmetric presence qualification, explicit startup and invalid-data handling | [Inputs](docs/inputs.md) |
| `events.h` | Schmitt rising edges, bounded pending event counts, explicit acquisition and overflow policies | [Inputs](docs/inputs.md) |
| `controls.h` | Crossing pickup in a caller-mapped domain, endpoint-aware motion acceptance, neutral zones, discrete hysteresis | [Controls](docs/controls.md) |
| `gestures.h` | Press-time role ownership; consuming a gesture suppresses its release action | [Controls](docs/controls.md) |
| `timing.h` | Mechanical button qualification with separate press and release durations | [Timing](docs/timing-and-transitions.md) |
| `pickup.h` | Stateful pickup in caller-mapped bounds, unreachable-target status, explicit rearm and invalid-gap handling | [Pickup](docs/pickup.md) |
| `pulses.h` | Logical pulse expiry, restart/ignore retrigger policies, immediate cancellation | [Pulses](docs/pulses.md) |
| `trigger_delay.h` | Bounded per-input trigger identity across caller-owned ticks | [Trigger delay](docs/trigger-delay.md) |
| `transitions.h` | Retain the latest requested destination until an explicit commit boundary | [Transitions](docs/timing-and-transitions.md) |

Each header works independently, with no third-party runtime dependency, heap allocation, exceptions or hardware SDK. Components use per-instance or caller-owned state and require one owner or external synchronization. Board adapters supply samples, validity, scaling and time; the application decides routing, musical boundaries, display feedback and recovery policy, and chooses filtering durations and electrical thresholds for the actual circuit. Compile input validation with ordinary finite/NaN semantics; `-ffast-math` and equivalent finite-only assumptions are unsupported.

## Use it in a build

Copy `include/eurorack_patterns/` plus `LICENSE` and `ATTRIBUTION.md` into your project and add the parent include directory, or use a pinned CMake dependency:

```cmake
include(FetchContent)
FetchContent_Declare(eurorack_patterns
  GIT_REPOSITORY https://github.com/lylepmills/eurorack-patterns.git
  GIT_TAG b6655e71559cd003ec69f73415df5ab89b0b799b) # v0.2.1
FetchContent_MakeAvailable(eurorack_patterns)
target_link_libraries(your_firmware PRIVATE eurorack_patterns::eurorack_patterns)
```

This full commit pin selects immutable release v0.2.1. Each [release](https://github.com/lylepmills/eurorack-patterns/releases/latest) supplies its own full commit pin; use the tested version you intend to ship. Tests default off when included as a subproject. An installed package also supports `find_package(eurorack_patterns CONFIG REQUIRED)`.

## Build and test

The host checks require CMake, a C++ compiler and Python 3.9 or newer. Python supports repository checks and optional capture/replay tools; it is not a library dependency.

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
```

Tests remain active with `NDEBUG`. They cover invalid and duplicate evidence, insertion chatter, noisy slow movement, exact endpoints, pickup reversal, gesture consumption, event overflow, timer wrap, rapid destination changes, unreachable pickup, pulse retrigger/cancellation, and delayed input identity. Deterministic reference models and bounded trace enumeration supplement the example traces. To enable address and undefined-behavior sanitizers on GCC or Clang, configure with `-DEURORACK_PATTERNS_SANITIZERS=ON`.

The commands above run the portable tests without downloading measured traces. Add `-DEURORACK_PATTERNS_BUILD_BENCH_TESTS=ON` to compile and test the Daisy adapter and capture simulations; full measured replay is a separate opt-in described in [evidence downloads and test boundaries](docs/evidence.md). Reports stay in Git, while the large recordings and original development history are preserved as hash-verified release assets. The [Daisy code map](examples/daisy/README.md) and [bench record](docs/bench/daisy.md) preserve bounded control/jack results and failed cases. That campaign is closed; its separate clock investigation remains unresolved.

## What this is not

- **Not a hardware qualification.** Host tests use synthetic traces, labeled separately from the measured Daisy recordings, and this release does not claim validation on a production module.
- **Not a catalog of implemented features.** A catalog entry is not necessarily an implemented component; the coverage map separates implemented mechanisms from application recipes and hardware measurements. Clock tracking, audio fades, storage backends and electrical protection remain documented patterns with their conditions and proposed checks, not problems this library silently treats as solved.
- **Not thread-safe.** Components do not make an interrupt/foreground handoff thread-safe; one owner or external synchronization is required.
- **Not a control policy.** The library never decides routing, musical boundaries, feedback or recovery; those belong to the application and its circuit.

## License, provenance and versions

MIT, copyright 2026 Lyle Mills. Commercial use and modification are welcome; preserve the required notices. The catalog credits makers beside each observation, and [ATTRIBUTION.md](ATTRIBUTION.md) records source revisions and the distinction between inspiration, adaptation, and copied code. Linked manuals and projects retain their own licenses.

Version 0.2.1 is the latest release and preserves the 0.2.0 library interfaces and behavior. `main` additionally carries unreleased documentation, example, test and bench changes, listed in the [changelog](CHANGELOG.md); the nine public headers are unchanged since 0.2.0. The API is still pre-1.0: pin a release and run your product's integration tests when updating. Changes to behavior or public interfaces will be described in the changelog. Maintainers follow the [release checklist](docs/releasing.md), including public-content review and immutable releases.
