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
experiment. Both the initial controls and the newer event-triggered fault/startup
scenarios have bounded physical evidence below. Public library headers are
unchanged. The host suite has 32 CTest entries, including protocol/mock-serial
tests, synthetic scenarios, scope-alignment rejection tests and 15 complete
measured replays. The firmware itself is not simulated by those host tests.

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

The exporter accepts the reviewed protocol 1/2 identity and fixture fields only.
For startup captures, specify `--startup-kind reset` or `--startup-kind usb-power-cycle`
from the recorded operator procedure. Review any new identity fields before
extending the allowlist; add independent expectations before treating a trace as a pass.

### Active fault and startup measurements

Measured on 2026-10-15 and 2026-10-16 in America/Los_Angeles, on the same Seed3,
B100k pot and normally open button fixture. The [second corpus](../tests/measured/daisy/2026-10-16)
contains nine complete runs totaling 609,923 observations. Each file identifies
its actual acquisition timestamp, firmware commit/build and binary hash. The
fault-button runs used firmware commit `9b5442910fd9f4e9851c56b5a80e07e1f245137f`;
the longer movement and startup runs used `5c9b10e9d344e103421d763eeb97c2c85fe57f7f`.

| Experiment | Observed result |
| --- | --- |
| Service gap during a held press or across its hold threshold | Cancelled press and eventual release caused no action; a later fresh tap acted once. Each gap was approximately 27 ms and accounted for 26 skipped service slots. |
| Service gap during release qualification | Interrupted tap cancelled; release qualification restarted after the gap. A subsequent fresh tap acted once. The approximately 26 ms gap accounted for 25 skipped slots. |
| ADC-only invalid interval during a tap | Button sampling continued; the first release/action occurred inside the 250 ms ADC gap, and the second tap acted normally. Invalid ADC samples were not applied. |
| Upward and downward pickup crossings hidden by a one-second ADC gap | Output held at 25% through the unobserved crossing and recovery. The later observed reverse crossings acquired at 25.0462% and 24.6983%, within the configured tolerance. Scope analog medians corroborated the crossings during invalidity. |
| Target changed while the knob moved | Pickup first acquired at 25.0004%. A raw midpoint crossing changed the target to 75%, revoked ownership, and held that value for 3.181 s until reacquisition at 75.0134%. |
| Physical RESET, released button, high knob position | All 20,000 application samples matched the scope; no button actions or unintended pickup. |
| USB power-on with button held and knob near midpoint | Initial hold and release caused no action. One fresh 131.292 ms tap acted once, 10.863 ms after release. ADC and analog midpoint readings stayed consistent. |

All nine runs have verified transport and C++ replay, complete application
service-pulse coverage and sampled button agreement, with no unexpected skipped
slots or ADC failures. Gaps are deliberate software invalidation or foreground
stalls; they do not establish physical disconnection detection or audio/IRQ-load
behavior. The [new measured checks](../tests/test_daisy_fault_measured.py) preserve
these expectations alongside the first-pass regressions.

Reset and power-on captures included a roughly 2.287-second high service-marker
level **before application sampling**. It ended about 130 ms before the first
application pulse. A released button input also changed electrical level before
its application sampling began. These observations remain explicit in exported
metadata; their electrical/boot-stage cause is not established here. The
[scope matcher](../tools/daisy_scope.py) accepts only the reviewed long prefix,
then matches every application pulse by count, timestamp, interval and recorded
work width. Unknown extra pulses, missing pulses and timing mismatches fail.

Protocol 2 exports retain actual analog sample rates, service-gap intervals and
10 ms voltage medians, with pre-application analog medians for startup captures.
Medians are rounded to six decimals for reproducibility, not calibrated precision.
Full original USB windows remain losslessly compressed; native scope files remain
private and are represented by hashes. These derived analog data are not full-bandwidth
noise or transient measurements.

Untriggered operator windows and disconnected-probe recordings were retained
privately and excluded from these published passes. A disconnected analog probe
read approximately zero while the MCU continued reporting valid full-scale ADC
conversions. Reconnecting the probe restored agreement. This is a measurement
fault, not evidence that the ADC's conversion-success flag detects cable health.
Longer fixed windows provided about two minutes for the operator to begin while
retaining the complete waiting period.

This remains one fixture and a small set of manually operated runs. Remaining
work includes repeated/varied startup and fault phases, other pots and boards,
broader audio/IRQ workloads, real jack/gate circuitry, pulse/CV timing, and a
separate power-cut/brownout/storage campaign. No library control behavior changed
as a result of this pass.

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
rate. The first **application** D0 service-marker pulse aligns the run with the USB trace,
subject to the small GPIO/timestamp instruction offset. These D0/D1 names refer
to Daisy pins, not the scope's channel numbers. D0 width includes acquisition,
state updates, record storage and synthetic foreground load; `work_us` excludes the final
marker write. D1 marks the action immediately after the state update. Save the
native Saleae recording with the USB evidence. Saleae capture is currently
operator-controlled; the Python tool captures USB, not the MSO.
For startup, retain pre-application transitions separately; a reset-time high
level is not automatically an application service pulse. Use complete-window
timing/width checks rather than dropping unexpected edges until counts agree.

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

### Audio/USB load and continuous soak

Three complete paired stationary traces from the first load pass are available
in [the measured corpus](../tests/measured/daisy/2026-10-16-load), with
[replay and physical-evidence checks](../tests/test_daisy_load_measured.py).
Each contains 10,000 observations on the same Seed3/B100k fixture, with the pot
near its midpoint and button released. All service pulses matched; no missed
slots, ADC failures, unexpected actions or callback timing flags occurred.

| Recorded workload | Maximum physical service interval | Maximum physical service width |
| --- | --- | --- |
| Audio stopped, no USB traffic | 1000.383 us | 141.234 us |
| Real DMA callbacks, no padding or USB traffic | 1004.978 us | 145.576 us |
| 650/1000 callback padding, 16-frame blocks, requested 500 USB packets/s | 1229.155 us | 566.010 us |

These are extrema from bounded recordings, not universal deadlines or calibrated
accuracy claims. The separate short matrix also passed at 48-frame blocks, but
its firmware-reported maximum interval reached 1669 us. **Block size changes
worst-case foreground latency even at the same callback padding fraction.**
Control validity and button behavior still need testing while an operator moves
the controls under these loads. Production DSP, other interrupt priorities,
display/storage work and other boards remain separate qualification work.

The fixture's actual callback rate was about 3000.9/s at 16-frame blocks. Host
USB delivery was below its requested rate; skipped host send slots remain in
the evidence and are not attributed to device loss. Every sent packet in these
published windows matched the device count and sequence checks. Physical scope
alignment kept the existing bounds: under 5 us timestamp/interval mismatch and
under 3 us work-width mismatch; observed errors were around 1 us or less.

Two counterexamples remain explicit in the same corpus:

- **Scheduling boundary, independently verified:** at 96-frame blocks and
  650/1000 padding, with no USB traffic, a complete 10-second trace contained
  8,407 observations and 1,593 skipped control slots. No audio callback exceeded
  its own period. Scope alignment passed, with a 2000.020 us maximum service
  interval. The nominal-service check correctly fails. Meeting the audio
  deadline does not guarantee the control deadline, even with average CPU
  headroom. The replay checks the actual observations; it does not invent the
  skipped ones.
- **30-minute soak, not qualified:** all 1,800,000 observations, 5,401,612 audio
  callbacks and 796,049 received USB packets were accounted for. Device counters
  reported no missed slots, ADC failures, malformed packets or button actions;
  all 1,800,000 physical service pulses were present. However, nine one-second
  buckets between seconds 1611 and 1668 disagree with the scope's local maxima
  by up to 22.016 us for intervals and 20.312 us for widths. The cause is
  unresolved. Whole-run maxima agree within 1 us and would hide this discrepancy.
  The unchanged 5/3 us local bounds reject it. The complete aggregate wire record
  and a declared two-second scope excerpt reproduce the rejection in regression
  tests; passing that regression means detecting the disagreement, not passing
  hardware qualification. Native originals remain retained. Next instrumentation
  should measure raw-timer-to-marker timing and local timing bounds before
  repeating the soak; do not widen bounds or attribute this to the control
  library without evidence.

The optional `L` command starts the Seed3 codec's real stereo SAI/DMA callbacks
at nominal 48 kHz. Outputs are silent and inputs are ignored; the existing
pot/button/marker wiring is sufficient. This is a scheduling experiment, not an
audio-quality or production-DSP workload measurement. Normal captures and the
automatic startup recorder leave audio stopped. No QSPI write or erase is added.

`audio-permille=-1` disables audio; `0` exercises DMA and the SDK conversion path
without extra work; `1..700` pads the application callback body to that fraction
of its nominal period. The default matrix uses 250 and 650, with 16- and 48-frame
blocks; 96 is also supported. This padding is synthetic work in a real audio IRQ,
not a claim that a particular synth occupies that CPU percentage. Measured body
time excludes SDK conversion and the rest of IRQ handling. Callback count, maximum
body/interval time, over-budget bodies, >1.5-period intervals and wrong block sizes
are retained. These counters cannot prove that the codec had no underruns.

USB load is host-to-device traffic at a requested 100 or 500 64-byte packets/s.
The IRQ checks packet contents and sequence across arbitrary USB chunk boundaries;
traffic cannot enter the command mailbox. Host pacing is best effort. Both sides'
counts, host skipped send slots/maximum lateness, malformed frames and sequence
errors remain explicit. A run fails its stimulus checks if counts differ, fewer
than 80% of the expected active-window packets arrive, more than 20% of host
slots are skipped, or host pacing pauses exceed 50 ms. This does not exercise
simultaneous USB transmit traffic or storage I/O.

After downloading the retained startup window, use the matching manifest and
replay executable from the build above:

```sh
python3 examples/daisy/load_capture.py capture --port PORT --manifest build-daisy/manifest.json --out build-captures/load-trace --mode trace --seconds 150 --audio-permille 650 --block-size 16 --usb-hz 100 --replay build/daisy_replay
python3 examples/daisy/load_campaign.py --dry-run
python3 examples/daisy/load_campaign.py --port PORT --manifest build-daisy/manifest.json --out build-captures/load-campaign --replay build/daisy_replay
```

For an interactive trace, retain the 150-second operator window and record the
intended gesture independently. Start the scope first and verify complete service
coverage afterward. Short IRQ-masked instrumentation windows keep the starting
marker, timestamp and button read together, and the ending work timestamp and
marker together. They are part of this adapter's measured interrupt latency.
A mismatch with the first-pass tight alignment bounds requires investigation,
not silent trimming or wider acceptance after seeing the result.

The stationary campaign runs seven full-trace cases (baseline, audio DMA, two
padding levels, USB alone, and combined loads at two block sizes), followed by
one **continuous 30-minute soak**. Keep the button released and pot still.
It stops at the first failed check and preserves that run. `--soak-seconds` can
select 1..3600 seconds for bring-up or a longer follow-up. The short cases are
separate acquisitions; only the final soak is continuous. Neither script captures
Saleae channels or flashes/resets a device.

Trace mode retains every sample for the existing C++ replay, up to 150 seconds.
Soak mode keeps servicing controls throughout, retaining a fixed-size aggregate
for every second: counts of samples, skips, errors and button actions, cadence breaks, first/last
timestamps, maximum work/interval time and valid ADC range. It supports one hour
without a RAM buffer wrap. These aggregates are **not individually replayable**
and cannot establish the exact shape of a transient or a missed pickup crossing.
Pickup ownership and value changes are not retained in these aggregates; use
full traces to check that behavior. Digital-only soak recordings also do not
establish analog wiring or voltage stability throughout the window.
No USB output or download interrupts either acquisition; records transfer after
audio stops. The timer is extended across raw counter wraps before conversion.

The load envelope has its own `load_protocol=1`, echoed configuration and whole
response checksum around unchanged protocol-2 control traces or `S` aggregate
records. The host rejects incomplete/reordered/count-inconsistent data and saves
raw bytes before validation. Nominal-load gates require complete service-slot
coverage, no unexpected skips/ADC faults/cadence breaks or callback budget/interval
faults, and plausible callback coverage within 0.5% (at least three callbacks)
of nominal timing. Stationary runs additionally require zero button actions.
A machine pass still says independent scope/behavior review is pending.

Host tests exercise framing, corrupt/missing evidence, failed measurement gates,
mock serial interruptions, hour-long aggregate accounting and timer wrap. Begin
new hardware qualification with paired baseline and DMA-only captures before
ramping the load. Each measured trace identifies its exact firmware build.

The [trace exporter](../tools/export_daisy_trace.py) accepts complete stationary
load traces with `--load --pot-ohms 100000 --capacitor-nf 0`. It requires an
explicit fixture declaration, full physical pulse/input coverage and replayable
control records. Passing machine checks are the default; a counterexample
requires `--expected-status fail` and retains its failed quality result. The
[soak exporter](../tools/export_daisy_soak.py) checks every digital service pulse
against the per-second aggregate counts and maxima. It fits clocks within each
second to allow slow oscillator drift over long recordings without hiding
interval/width mismatches. It does not reconstruct individual observations.
An expected failed quality outcome must be declared explicitly when exporting
a complete soak counterexample; an independent timing disagreement requires
`--expected-scope-status fail`. Neither becomes a qualified pass. The soak
export retains an explicit local edge excerpt when timing comparison fails.
Both exporters
retain wire bytes and use an explicit metadata allowlist, excluding native
vendor metadata and arbitrary host error text.

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
