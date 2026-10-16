# Evidence and validation

Source confidence and product qualification are different. A verified fix can motivate a good contract; a host test can establish that our implementation follows it; neither proves that a chosen threshold, scan cadence or electrical interface works on a particular module.

## Executed host checks

The suite combines synthetic adversarial fixtures with the explicitly labeled [Daisy measurements below](#first-daisy-measurements). The published 0.2.1 release predates those measurements. The CMake tests use always-active checks in release builds, compile as C++11 with warnings as errors and no exceptions/RTTI, compile every public header independently, and exercise an installed-package consumer. The existing CI matrix covers Linux, macOS and Windows; Linux enables address and undefined-behavior sanitizers. The second pass also ran the local suite with those sanitizers on Apple Clang.

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
experiment. The first firmware has bounded physical evidence below. **The newer
event-triggered scenarios and automatic startup recorder are cross-built and
host-tested; their physical measurements remain pending.** Public library headers
are unchanged. The host suite has 28 CTest entries, including 18 Python
protocol/mock-serial tests, 13 synthetic protocol scenarios and six measured
replays. The firmware itself is not simulated by those host tests.

### First Daisy measurements

Measured on 2026-10-14 in America/Los_Angeles (some UTC acquisitions are dated
2026-10-15), using one Seed3, a B100k linear pot without an added capacitor,
a normally open button and paired Saleae MSO captures. The measured firmware is
commit `cc730b48d3284561ea4cbf9fde907be3acf4f98c`, build ID
`1f0d42db39622ab699e03d0b`; subsequent firmware must establish its own evidence.

Twelve selected complete paired runs contained 199,974 serviced observations.
Six complete windows (136,000 observations) are included as
[losslessly compressed wire traces](../tests/measured/daisy/2026-10-14), with
allowlisted provenance and scope-derived button/action edges beside each file.
These are recorded inputs; the ADC gap is explicitly a software injection.

| Observation | Result and boundary |
| --- | --- |
| Five short taps and one approximately two-second hold | Exactly five tap actions and one hold; no action on hold release. Tap latency from physical release 10.16–11.13 ms; hold about 610.73 ms from physical press. One observed bounce cluster spanned about 109 us. |
| Ascending and descending pickup | Acquired at 25.0752% and 24.8859% for a 25% target; no earlier overwrite. Ascending capture ended before the clockwise endpoint. The descending repeat's 99-to-1% travel took 3.151 s; it was not an actual one-second sweep. |
| Settled endpoint | Descending repeat ended at output zero with no output changes during the last five seconds, despite raw ADC variation. Separate clockwise capture established ADC full-scale reachability. |
| Invalid observations while tracking | 250 deliberately invalid samples did not change the owned value; tracking resumed on the next valid observation. Pot was stationary. |
| External target edit | A stationary input did not overwrite the new 0.75 target; pickup rearmed. |
| Initially held button | Initial hold/release ignored, then one fresh tap accepted. This was initialization at **run start**, not power-on. |
| Deliberate stall and foreground load | Stall accounted for 26 skipped slots and a measured 27.000692 ms service interval. A separate 400 us busy-loop load had no missed slots. Neither exercised audio/interrupt load. |

All twelve selected runs had complete checksummed transport, matching replay and
scope coverage, and no unexpected missed slots or ADC failures. An earlier
maximum-length download was incomplete; buffered host reads fixed the observed
failure, without establishing the exact OS/USB failure mechanism. A possible
pot contact disturbance invalidated another run for clean-fixture conclusions;
the inspected/reseated repeat is the published descending trace. Early wiring
and scope-coverage failures remain retained privately and excluded from passes.

[The exporter](../tools/export_daisy_trace.py) preserves the original complete
USB bytes and derives relative digital edge times from native recordings. It
checks every service pulse and sampled button level, then copies only allowed
metadata fields. Original and compressed hashes, firmware identity and hashes
of native scope source files are recorded. Device identifiers, local paths and
operator notes are excluded. Full native originals remain retained privately;
the public edge extracts are a subset, not a complete analog recording.

[The measured regression](../tests/test_daisy_measured.py) verifies hashes,
replays the recorded input, and checks explicit outcomes and scope timing
bounds established in the bench review. Replay tests the application adapter;
it does not replace independent physical observations. These measurements do
not choose universal thresholds or establish electrical disconnect detection,
calibrated analog accuracy, jack behavior, power-cycle behavior or portability.

To export another reviewed capture, use an environment containing
`saleae-mso-api` 0.5.8; the exporter reads saved files and never opens hardware:

```sh
python tools/export_daisy_trace.py --capture CAPTURE_DIRECTORY --out-prefix tests/measured/daisy/DATE/CASE
```

The exporter deliberately accepts only the first fixture/protocol's known
identity and wiring metadata. Extend its allowlist after reviewing a new
fixture; add independent expectations before treating a new trace as a pass.

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
Protocol 2 firmware first records an automatic startup window; download it
before requesting a normal run. The host also accepts archived protocol 1 traces.

```sh
python3 -m venv build-tools
# Activate that environment using your shell's activation command.
python3 -m pip install pyserial==3.5
python3 examples/daisy/capture.py capture --port PORT --manifest build-daisy/manifest.json --out build-captures/startup --scenario startup --seconds 20 --replay build/daisy_replay
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
| `press-stall` | First observed fresh raw press schedules a nominal 25 ms service stall 100 ms later. Hold, release, then make a fresh tap: interrupted press must not act; fresh tap must work. |
| `hold-stall` | Same, with the stall scheduled 605 ms after the raw press, around the illustrative hold boundary. |
| `release-stall` | Stall on the next loop after the first observed release of a fresh press, before release qualification. Use a short press, then a separate fresh tap. |
| `press-adc-gap` | First fresh raw press schedules a 250 ms ADC gap beginning 20 ms later. Button observation continues: a roughly 100 ms tap during the gap should still act once. |
| `pickup-gap-up` | Crossing raw code 9831 (about 15%) upward schedules a one-second ADC gap at the next observation. Start below that point and move past the 25% target during the gap. Waiting pickup must not infer the missing crossing; a later observed crossing should acquire. |
| `pickup-gap-down` | Equivalent descending test, crossing raw code 22937 (about 35%) from above before the gap. |
| `moving-target` | Crossing raw code 32768 upward edits target to 0.75 before that sample is applied. Continue upward to reacquire. |
| `startup` | Downloads the retained 20-second automatic post-initialization capture, target 0.25. Does not start a new run. |

Normal runs last 1–150 seconds on the expanded-buffer firmware; original images
remain limited to 30 seconds. The host checks the advertised capacity before
sending a run command. For an operator-led test, use `--seconds 150`: begin within
the first two minutes and leave time for the complete sequence and recovery.
Keep the entire waiting period in both recordings. This is a fixed full window,
not a rolling or movement-started capture; the stimulus still triggers on the
physical input. Arm the scope for the whole window plus setup margins. Longer
windows need more capture storage and download time. The 150,000-record buffer
uses 10.2 MB of SDRAM in the ARM link map; the automatic startup window remains
20 seconds.

Scheduled-fault/target scenarios require at least six seconds.
Movement-triggered scenarios use target 0.25. Event triggers use raw input
observations, independently of the gesture or pickup result under test. Start
with button released; an initially held button does not supply a fresh press.
The first matching edge triggers the stimulus once. Raw bounce may affect trigger
time; inspect the scope and recorded timestamps rather than assuming a clean edge.

Protocol 2 adds `STIMULUS,trigger_us,begin_us,end_us` before `COLUMNS`; its bytes
and the data records are checksummed together. `-1` means that phase was not
observed. The host independently checks trigger edges, scheduling and recovery.
A complete download with an untriggered or unfinished scenario returns exit code
3 and retains its evidence; it is not a completed experiment. Completion means
the stimulus occurred, not that the intended human interaction overlapped it or
that behavior passed. Confirm those conditions in the scope/behavior review.

### Automatic startup recording

Start the scope **before** reset or power-on. The firmware initializes clocks,
RAM, GPIO and ADC, then samples the initial button state and records 20 seconds
without USB initialization or host commands. USB enumerates afterward; use
`--scenario startup --seconds 20 --target 0.25` to retrieve that retained window.
The existing marker pins and pot/button wiring are unchanged.

For a held-button test, hold before reset/power-on, release several seconds into
the service-marker window, then make one fresh tap. Also capture released-button
boots at endpoints and midpoint. Require no unintended actions or ownership,
then normal recovery on a fresh interaction. Keep reset and power-on observations
separate; neither is brownout or storage-atomicity qualification.

`B,TOKEN` retrieves the buffered startup window; its `START` line is emitted at
download time, not acquisition time. Match scope coverage to service-marker
edges. A successful firmware download consumes the startup availability flag;
a new reset is needed for a new startup capture. A normal run is refused while
an unread startup window remains. A failed firmware transmission retains it for
retry; a host failure after successful transmission may require another reset.
No persistent settings or automatic reset command is involved.

This observes the application **after peripheral initialization**. It does not
capture supply rise, ROM/bootloader execution, or clock/RAM/ADC setup. Record
those separately if the question concerns earlier electrical/startup behavior.

### Transfer integrity

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
