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

## Integration preparation in 0.2.1

The release adds a host-tested shared-knob adapter, a complete takeover/reset
walkthrough and three synthetic illustrations generated from checked executable
traces. CI checks illustration freshness. The public core headers are unchanged.
The host suite has 24 checks, plus installed-package consumers. A separate ARM
build instantiates all nine headers and compiles each independently for Cortex-M0+.
The optional Pico SDK example links a firmware ELF using the same adapter.
These cross-builds establish compiler/SDK compatibility only: the Pico has not
been flashed or measured as part of this release. See its [remaining bench
checks](../examples/pico/README.md#adapter-decisions-and-checks-still-needed).

## Daisy Seed3 control bench

The [firmware](../examples/daisy/main.cpp), [builder](../examples/daisy/build.py)
and [capture tool](../examples/daisy/capture.py) prepare a reproducible control
experiment. **Cross-built and host-tested only; no physical measurements yet.**
The public library headers are unchanged. This adds two CTest entries (26 total);
one runs eight Python protocol/mock-serial tests and five synthetic C++ replays.
The firmware itself is not simulated by those tests.

### Fixture and Saleae connections

Wire with power disconnected. Physical pin numbers below are for **Daisy Seed3**;
use its [official pinout](https://daisy.nyc3.cdn.digitaloceanspaces.com/products/seed3/Seed3-Pinout.pdf)
for orientation. A B100k linear pot is the initial fixture. Keep wires short and
start without an added capacitor. No audio or external CV source is needed.

| Connection | Physical pin / signal |
| --- | --- |
| Pot outer terminals | 21 / 3V3_A and 20 / AGND |
| Pot wiper; Saleae analog probe tip | 22 / D15 / A0 |
| Normally open button | 15 / D14 to 40 / DGND; internal pull-up enabled |
| Required ground jumper | 20 / AGND to 40 / DGND |
| Saleae digital input: raw button | 15 / D14, active low |
| Saleae digital input: service marker | 1 / D0, high around each serviced observation |
| Optional Saleae digital input: gesture marker | 2 / D1, toggles once per tap/hold action |
| Scope and logic probe ground | 40 / DGND |

Use the MSO's 10x scope probe on the wiper and match its software attenuation;
the supplied probe is approximately 10 MΩ in parallel with 15 pF. Record actual
probe settings and any filtering added later. All grounds are common. ADC and
logic signals in this fixture stay between ground and 3.3 V. Eurorack voltages
require a separate protected input circuit.

Start Saleae recording before requesting a run. Use DC coupling for the wiper
and an appropriate 3.3 V digital threshold. A digital rate of at least 1 MS/s is a
reasonable starting point for the service/button markers; record the actual
rate. The first Daisy D0 service-marker edge aligns the run with the USB trace,
subject to the small GPIO/timestamp instruction offset. These D0/D1 names refer
to Daisy pins, not the scope's channel numbers. D0 width includes acquisition,
state updates, record storage and synthetic foreground load; `work_us` excludes the final
marker write. D1 marks the action immediately after the state update. Save the
native Saleae recording with the USB evidence. Saleae capture is currently
operator-controlled; the Python tool captures USB, not the MSO.

The onboard LED shows pickup ownership during a run. It retains the last state
afterward; it is not a progress indicator or a voltage readout.

### Build without accessing hardware

Use an ARM GNU embedded toolchain on PATH and CMake 3.24 or newer. The tested
libDaisy revision is 7.0.1, pinned for reproducibility. Initialize these SDK
submodules in a separate checkout; the builder only reads that checkout and
builds its sources in the output directory.

```sh
git clone https://github.com/electro-smith/libDaisy.git ../libDaisy
git -C ../libDaisy checkout e1f740a5a7fe38e6d6d41281bf99fe7a2bb3827b
git -C ../libDaisy submodule update --init Drivers/CMSIS-DSP Drivers/CMSIS_5 Drivers/CMSIS-Device/ST/STM32H7xx Drivers/STM32H7xx_HAL_Driver Middlewares/ST/STM32_USB_Device_Library
python3 examples/daisy/build.py --libdaisy ../libDaisy --out build-daisy
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build -C Release --output-on-failure
```

`--gcc /path/to/toolchain/bin` can select a compiler outside PATH. The output
contains `patterns_daisy.bin`, `.elf`, `.map` and `manifest.json` with source,
dependency, compiler and artifact hashes. The binary is a Daisy bootloader SRAM
application stored at **0x90040000**, not an internal-flash bootloader image.
The builder and capture tool contain no flashing/reset commands. Before a
separate flashing session, establish exclusive board ownership, check the
installed bootloader and retain a verified way to restore the prior application.
No bootloader, asset or settings region should be overwritten by this test.

### Capture and replay

Install pyserial in a local environment. Capture requires an explicit port and
the matching build manifest/binary. It sends an identity query first and refuses
to start a run on a different firmware build. It does not auto-discover boards,
assert reset lines, write persistent settings or put the board into DFU.

```sh
python3 -m venv build-tools
# Activate that environment using your shell's activation command.
python3 -m pip install pyserial==3.5
python3 examples/daisy/capture.py capture --port PORT --manifest build-daisy/manifest.json --out build-captures/stationary --seconds 20 --scenario manual --replay build/daisy_replay --notes "Stationary pot near midpoint; button untouched"
python3 examples/daisy/capture.py analyze build-captures/stationary/raw.txt --out build-captures/stationary-replay --replay build/daisy_replay
```

On multi-configuration builds the replay executable is typically
`build/Release/daisy_replay.exe`. `--pot-ohms`, `--capacitor-nf`, `--probe` and
`--notes` record the operator-declared fixture; defaults describe the 100k/no
capacitor/10x-probe setup above. Keep notes generic and remove device serials or
private information before publishing. Each output directory must be new.

| Scenario | Behavior |
| --- | --- |
| `manual` | Initial target 0.25 (override with `--target 0..1`). A tap alternates 0.75/0.25 on qualified release. A 600 ms hold sets 0.5 once and consumes release. |
| `targets` | Also re-arms at 0.75 after five seconds, then alternates 0.25/0.75 every five seconds. |
| `gap` | Skips ADC acquisition from 5.000 to 5.250 seconds, explicitly marking those observations invalid; continues observing the button. |
| `stall` | Stops foreground service for a nominal 25 ms at five seconds. Counts skipped deadlines; breaks pickup continuity and cancels a pending gesture. |
| `load` | Adds a timed 400 µs foreground busy loop per observation. This is synthetic CPU occupancy, not audio/interrupt/storage-load qualification. |

Runs last 1–30 seconds; scheduled-fault/target scenarios require at least six.
No USB output occurs during acquisition. Records are buffered in SDRAM, then
transferred; allow time for the download. An unplugged host does not stop an
in-progress window. The host drains available serial data in bounded blocks and
assembles lines in memory, avoiding one operating-system read per byte. This
reduces receiver overhead; framing and checksum checks still determine whether
the transfer is complete. Interrupted or malformed downloads remain incomplete
and retain their original bytes; rerun into a new directory rather than treating a
partial trace as a pass.

The tool saves original `raw.txt`, operator/build `metadata.json`, lossless
integer `samples.csv` and a `summary.json`. It verifies framing, run identity,
sequence order, record count, checksum, deadline accounting, validity flags and
basic application invariants. Optional C++ replay runs recorded inputs through
the same application adapter and compares every reported state/event/value
(with one-millionth rounding tolerance). This proves replay consistency, not an
independent oracle for physical events. Port/device serial identifiers are not
stored automatically.

Values ending in `_ppm` are normalized values multiplied by one million;
`accepted_ppm = -1` means no currently valid motion anchor. State numbers are
0 unarmed, 1 waiting, 2 tracking, 3 unreachable. `gesture` is 0 none, 1 tap,
2 hold. Timestamps are microseconds from the start of each run, using extended
raw timer ticks before unit conversion. `adc_us` covers start/poll/read/stop;
conversion-complete polling establishes freshness, but not wiring health or
analogue accuracy. No ADC averaging or additional analogue filter is enabled.
The 810.5-cycle aperture must still be checked with the 100k source impedance.

### First measurements and acceptance

Start with stationary captures near both endpoints and midpoint, then slow and
fast sweeps in both directions. Repeat after target changes, with taps/holds,
with the button held at run start, and under each generated fault/load scenario.
Record actual intended tap/hold counts independently of the firmware's counters.
Before tuning, require:

- Zero transport loss, buffer overflow and unexpected ADC failures. Missed
  deadlines are reported explicitly; the stall's deliberate misses remain in
  the evidence. Unexpected misses in other scenarios need investigation.
- No applied sample while invalid or waiting; no crossing inferred across an
  acquisition gap. Already-tracking controls resume from the next valid sample.
- Exactly one action per intended tap/hold, no extra tap after a hold, and no
  action from a button held at startup or from a cancelled press across a gap.
- Scope evidence consistent with timestamps/action markers. Measure latency and
  bounce before deciding whether the illustrative 10 ms qualification, 600 ms
  hold, 0.5% pickup tolerance and motion thresholds feel appropriate.

Raw spread during movement is not a stationary-noise measurement. Endpoint
reachability requires a separate check of the real pot's attained ADC range;
this fixture does not calibrate or stretch it automatically. Preserve original
failures before tuning. No jack contact, external gate, audio deadline, flash
persistence, or calibrated CV accuracy claim follows from this bench.
