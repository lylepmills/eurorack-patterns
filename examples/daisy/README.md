# Daisy measurement adapter

This optional Seed3 bench exercises the portable library with real controls,
switched-jack evidence and deliberate acquisition faults. It is a measurement
apparatus, not a production Eurorack front end. For a minimal application
integration, start with the [shared-knob walkthrough](../../docs/quickstart.md).

## Read or replay without hardware

- [Reusable findings and limits](../../docs/validation.md) explain what the
  campaign establishes.
- [Bench procedures and results](../../docs/bench/daisy.md) preserve the circuit,
  firmware settings, independent measurements and rejected captures.
- [Evidence downloads](../../docs/evidence.md) explain optional measured replay.
- [Clock investigation](../../docs/investigations/daisy-clock.md) is a closed
  fixture-specific study; its unresolved cause does not block the library.

Host simulations need no board or hardware SDK:

```sh
cmake -S . -B build-bench -DCMAKE_BUILD_TYPE=Release \
  -DEURORACK_PATTERNS_BUILD_BENCH_TESTS=ON
cmake --build build-bench --config Release --parallel
ctest --test-dir build-bench -C Release --output-on-failure
```

Run those commands from the repository root. Default builds omit this bench.

## Code map

| Files | Responsibility |
| --- | --- |
| `bench.h`, `experiment.h`, `load.h` | Control observations, ownership, startup and injected faults |
| `main.cpp` | Seed3 control acquisition and diagnostic transport |
| `jack_bench.h`, `jack_acquisition.h` | Probe evidence and bounded drive/settle/convert phases; missed evidence breaks qualification |
| `jack.cpp` | Board timers, ADC, audio/DMA workload and capture ownership |
| `pulse_generator.*` | Independent, finite electrical stimulus on a second board |
| `capture.py`, `load_capture.py`, `jack_capture.py` | Transport parsing, integrity and observation checks |
| `*_campaign.py`, `jack_*matrix.py`, `jack_session.py` | Bounded hardware-run orchestration |
| `dsp_workload.h`, `dma_*`, `clock_waveform.py` | Workload controls retained for the closed clock investigation |

The adapter depends on libDaisy and the documented Seed3 bootloader/memory
layout. `build.py` verifies its SDK pin and writes a build manifest. Its roles
are `bench`, `pulse-generator` and `jack-bench`; building does not flash a board.
Use the bench record for role-specific wiring and build commands. Do not connect
Eurorack voltages directly to MCU pins or treat this fixture as a protection
circuit. Numeric thresholds and interrupt priorities belong to this apparatus.
