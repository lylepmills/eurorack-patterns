# Integrate one shared knob

Start with `PickupLatch` when a preset, control bank or another owner can change a
parameter while its physical knob stays put. The latch owns pickup state; your
application owns mapping, movement acceptance, parameter writes and feedback.
Use the lower-level `controls.h` pickup predicates only when your application
already owns and tests that state machine. The percent convenience wrappers remain
supported; they do not automatically track invalid gaps or destination changes.

## Run the complete example

From a checkout of this repository:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build -C Release -R "example_pickup_workflow|test_shared_control" --output-on-failure
```

[`pickup_workflow.cpp`](../examples/pickup_workflow.cpp) runs the full sequence.
[`shared_control.h`](../examples/shared_control.h) contains the application adapter,
also used by the [optional Pico example](../examples/pico/README.md). These files
are examples, not installed library APIs or universal control settings.

1. `Reset(0.3f)` initializes a continuous destination in `[0,1]` and arms pickup.
   A distant first valid sample seeds history while the stored value holds; a near-target first sample can pick up immediately.
2. `Sample(percent, valid)` first rejects invalid, nonfinite or out-of-range input.
   It reports that gap to the latch **before** filtering movement. Otherwise a
   later sample on the opposite side could falsely imply a continuous crossing.
3. Valid input passes through `AcceptMotion` in physical percent. Its anchor is
   the last accepted position, so slow movement accumulates and endpoints remain
   reachable. After a gap the next valid sample establishes a fresh anchor.
4. Accepted positions map linearly to `[0,1]`. `Observe` grants permission to apply
   them once near/crossing pickup succeeds. The adapter turns that permission
   into a changed-value result; repeated valid samples are not repeated edits.
5. Every external edit, preset or bank change calls `ExternalEdit(target)`, even
   for an equal numeric target. It re-arms pickup and seeds the last accepted
   physical position if still valid. External values outside `[0,1]` are rejected
   without changing state. A real product may need a different recovery policy.
6. `Reset` discards all previous acquisition/ownership history. The example's
   accessors expose the value and latch state for UI feedback; the host decides
   how to show waiting, tracking or an unreachable target.

All calls here run in one execution context. For an ISR/foreground design, transfer
coherent samples through your own synchronized boundary and retain one owner for
the control state. A validity bit must reflect freshness and acquisition health;
range checks alone do not establish either.

The example's 0.6 percent motion threshold and 0.005 mapped-unit pickup tolerance
are demonstration settings, not measurements or hardware recommendations. It
assumes a continuous, monotone linear mapping. Restricted, reversed, nonlinear or
stepped mappings need their own bounds and destination policy; see the
[pickup contract](pickup.md). Test actual ADC noise and musician control feel.
For a destination with discrete values, the separate
[five-step example](pickup.md#one-stepped-destination-policy) shows one policy
for membership, pickup after snapping, readback and explicit recovery.

## Put the library in a firmware build

Copy `include/eurorack_patterns/`, `LICENSE` and `ATTRIBUTION.md`, or use the pinned
CMake dependency in the [README](../README.md#use-it). Installed consumers can use
`find_package(eurorack_patterns 0.2 CONFIG REQUIRED)`. The core has no board SDK
dependency. Compile with finite/NaN semantics: finite-only/fast-math modes invalidate
input checks. Keep DSP compilation flags separate when necessary.

The [ARM smoke build](../tests/embedded/CMakeLists.txt) instantiates all components
and compiles every public header alone for Cortex-M0+. Put `arm-none-eabi-g++` and
its companion tools on `PATH`, then run:

```sh
cmake -S tests/embedded -B build-arm -DCMAKE_TOOLCHAIN_FILE="$PWD/cmake/arm-none-eabi.cmake"
cmake --build build-arm
```

This creates object files, not a bootable firmware image or an execution result.
The Pico example additionally links against a real public SDK and board memory
layout. Neither build establishes timing, electrical robustness or control feel.
