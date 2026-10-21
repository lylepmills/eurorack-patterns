# Archived Daisy clock investigation

Large raw recordings and exact historical source revisions are preserved in the
[optional evidence archive](../evidence.md). Reports and replay tools remain in
this repository; these diagnostics are excluded from the default library tests.


**Closed, 2026-10-20; physical cause unresolved. No further bench work planned.**
The investigation began when real DSP/DMA loads produced disagreement between
firmware timing and an external instrument. It is retained as a fixture case
study, separate from the library's [contracts and validation](../validation.md).
The existing portable contracts do not depend on resolving this fixture
anomaly. A product that reproduces the behavior can evaluate it separately.

## What survives as a reusable lesson

- Check acquisition responsiveness and audio deadlines independently. Correct
  input-validity handling can preserve a stale state forever if acquisition
  never provides enough consecutive valid observations.
- Separate scheduling relative to an observed hardware clock from stability
  against an independent reference. A passing scheduling check does not erase
  a failed external timing check.
- Compare completed DSP/DMA work, not just requested load. Pin the binary and
  linker layout when isolating a buffer-placement change.
- Preserve receiver failures, missing coverage and ambiguous voltage evidence.
  A cleaner repeat does not prove the earlier failure's cause or repair it.

## Closing assessment

The scheduling defect was fixed in the Seed3 adapter and independently
[retested](../bench/daisy.md#scheduled-jack-acquisition-results). Later measured
clock behavior still depended on SDRAM address range under combined load. That
contrast survived a controlled firmware restoration, tested buffer offsets,
and an analog probe/input swap. None established an oscillator defect, an
audible codec problem or a portable rule to place DMA buffers at low addresses.

The final sixteen-capture plan completed with identical achieved work per run.
Six full receiver comparisons and ten short analog windows have different
coverage. The [final reports](../../tests/measured/daisy/2026-10-20-clock-waveform/summary.json)
and [native digest inventory](../../tests/measured/daisy/2026-10-20-clock-waveform/native-digests.json)
record their limits. The short analog windows cannot qualify the remainder of
each firmware run. Original failures remain in the measured regressions;
multi-gigabyte native voltage recordings are archived separately by hash.

Further probe-ground or circuit diagnosis may be useful for a product that
reproduces this behavior, but it is outside this closed campaign. Reopen only
for a named product decision or a reproducible violation of a reusable contract,
with a finite test plan and an explicit stopping rule.

## Historical methods and results

The accounts below preserve their original chronology, settings, acceptance
limits and unresolved results. References to the "next" experiment describe
the historical plan; they are not an active work queue. Do not assume any
listed wiring or firmware is currently installed.

### Jack DSP and memory-DMA campaign (partial hardware results)

Protocol 6 retains the scheduled acquisition and adds actual computation and
memory transfers in place of the timed audio busy loop. The prepared campaign
has **19 comparisons and four fault cases**, plus separate unloaded/loaded
early-finish checks. Five comparisons and both finish checks passed on hardware;
the first combined DSP/DMA case stopped the campaign on a reproducible timing
disagreement. The same two-board passive fixture,
generator firmware, D0–D4 probes and analog tip probe are sufficient. No audio
connections or manual plug movements are required.

The [DSP kernel](../../examples/daisy/dsp_workload.h) processes deterministic noise
through a 32-tap integer FIR and an SDRAM feedback delay for each voice. Four
and sixteen voices are exercised at 16/48/96-frame audio blocks. It computes
stereo samples, a sample hash, peak, nonzero-frame count and multiply-accumulate
count; the codec outputs remain silent. Every measured callback must contribute
exactly its block size to the signature. Host replay checks the full signature,
using the same kernel with analytic impulse/DC, reset and delay-wrap tests.
This establishes executed work and deterministic agreement, not an independent
audio algorithm implementation or codec sound quality.

The original protocol-6 [DMA workload](../../examples/daisy/dma_workload.h) exclusively owns DMA2
stream 6 and two disjoint, 32-byte-aligned SDRAM buffers. It requests 4 or 16 KiB
copies at 1 ms intervals, with at most one transfer outstanding and no queued
catch-up work. Each source word changes with the transfer number; every
destination word must match before the next transfer. CPU access and cache
maintenance bracket DMA ownership: clean the source and clean/invalidate the
destination before starting, then invalidate the destination after completion.
This follows ST's [Cortex-M7 cache-coherency guidance (AN4839)](https://www.st.com/resource/en/application_note/an4839-level-1-cache-on-stm32f7-series-and-stm32h7-series-stmicroelectronics.pdf).
Transfer buffers occupy complete cache lines separately from other data.

Acquisition retains interrupt priority 0, audio uses 1, and DMA2 completion uses
2. The completion handler publishes a result without polling, cache maintenance
or verification. Foreground code checks the data and enforces a 5 ms timeout;
an error stops the campaign and retains its evidence. Cache maintenance and
verification are part of the combined workload, so its cost is not attributed
solely to the DMA peripheral. Acquisition, audio deadlines and jack qualification
must pass their existing checks. Additional test budgets require at least 500
verified transfers per loaded second, no gap over 10 ms, coverage through the
loaded interval, and no transfer, checksum or corruption failure. Actual counts,
skipped launch opportunities and payload bytes are retained; 1 kHz is a request,
not a guaranteed throughput result. DMA timestamps report completion service in
the foreground, and the IRQ maximum includes preemption. D4 independently
measures audio callbacks, not the DMA2 bus.

Checksummed `JDSP` and `JDMA` records bind these results to the capture's plan.
DSP/DMA runs are limited to 30 seconds to bound counters. They cannot combine
with artificial audio padding. The [finite runner](../../examples/daisy/jack_dsp_matrix.py)
checks identities, starts the independent electrical clamp after acquisition
acknowledgement, stops at the first failed case and requires a new output
directory. It retains the host reference executable's hash. Existing protocol
1–5 recordings remain replayable.

```sh
python3 examples/daisy/jack_dsp_matrix.py --plan-only
python3 examples/daisy/jack_dsp_matrix.py --stage sweep \
  --port FIXTURE_PORT --generator-port GENERATOR_PORT --scope-id SCOPE_ID \
  --manifest BUILD/manifest.json --generator-manifest GENERATOR_BUILD/manifest.json \
  --dsp-reference build/test_daisy_dsp --out NEW_CAPTURE_DIRECTORY
```

The sweep includes bracketing baselines, two DMA-only cases, and five DSP/memory
profiles at each block size. The `faults` stage repeats insertion/removal ADC
gaps and acquisition pauses with four voices and 4 KiB transfers at 16-frame
blocks. The runner makes no real-cable, production-voltage, arbitrary-DSP or
long-soak qualification claim. Portable library headers are unchanged.

On 2026-10-20 UTC, firmware source `a6cee8ec6e570d0468f74f8537f8578fb390d020`
produced these [measured partial results](../../tests/measured/daisy/2026-10-20-jack-dsp).
At that stage the campaign was **incomplete**: one combined profile failed,
and seventeen planned comparisons had not run. Those original records do not
qualify combined fault recovery; the later explicit M-mode campaign below
provides separately classified scheduling/behavior evidence.

| Recorded case | Result |
| --- | --- |
| Unloaded baseline; DMA-only 4/16 KiB; 4/16 DSP voices without memory DMA at 16-frame blocks | Five full physical passes, 100,000 observations, no missing or late acquisition observations. Both DMA-only cases verified 7,999 transfers with no skipped launches. |
| Early finish, unloaded and four voices + 4 KiB DMA | Both full physical checks passed; 9,805 observations retained. The loaded run verified 3,465 transfers and replayed 166,384 DSP frames. Counts prove all launched transfers completed; they do not prove the finish request landed during a transfer. |
| Four voices + 4 KiB DMA, 16-frame blocks | Rejected twice. Complete 20,000-observation records, exact DSP signatures and all 7,999 DMA transfers verified, but global service alignment residuals reached 10.957 / 10.351 us against the unchanged 5 us bound. Adjacent-interval and pulse-width errors stayed below 0.7 us. |

A separate three-condition **clock diagnostic**, using the existing independent
open-drain generator, retained every visible stimulus edge and explicitly
accounted for edges hidden by a low probe signal. Across idle, DSP-only and
combined load, 25/21/34 visible generator edges fit the scope timeline within
0.199 us. The combined fixture record still had a 10.517 us service residual.
Audio callback cadence changed alongside the service clock in the combined
runs. This supports investigating the fixture's shared clock path; it does not
establish an oscillator, supply, thermal or timestamp defect. Generator and
scope are independent relative references, not calibrated absolute time.
All original rejections remain regression fixtures. Local fits are diagnostic
only and never replace the whole-record acceptance gate.

Firmware source `aaadfd5` adds an explicitly requested, at-most-ten-second **hardware
clock diagnostic**. `K?` identifies a separate diagnostic role; `K` starts an
otherwise identical capture with HSE/15 routed through MCO2 to PC9 (existing
D4 / physical pin 4). The [pinned ST HAL](https://github.com/STMicroelectronics/stm32h7xx-hal-driver/blob/404a70d4c19c124636c78801ff7c0dbc87bc4256/Src/stm32h7xx_hal_rcc.c)
configures that hardware output; no ISR toggles its edges. GPIO-low and the
previous MCO2 register fields are restored after each run. Normal `J` mode
continues to use D4 for audio callbacks. Diagnostic identity and `KSTART` records
are rejected by normal capture/review, so the two marker meanings cannot
silently share an acceptance path.

Seven subsequent recordings produced these
[hardware-clock results](../../tests/measured/daisy/2026-10-20-jack-hse): two normal
early-finish checks passed, bracketing three short clock diagnostics; a
ten-second combined-load diagnostic and unloaded repeat followed. All 58,000
diagnostic observations were present, with exact DSP signatures and verified
DMA payloads. The normal checks retained another 5,716 observations.

| Clock diagnostic | Original global service residual | Residual against counted HSE cycles |
| --- | ---: | ---: |
| Unloaded, 3 seconds | 0.207 us | 0.206 us |
| DSP only, 3 seconds | 0.259 us | 0.240 us |
| DSP + DMA, 3 seconds, load stops at 2 seconds | **5.195 us (rejected)** | 0.253 us |
| DSP + DMA, 10 seconds, load stops at 8 seconds | **14.703 us (rejected)** | 0.306 us |
| Unloaded after, 10 seconds | 0.230 us | 0.211 us |

In the full combined run, the relative HSE **period** scale was 28.7–31.5 ppm
above nominal during load, then 40.5–40.6 ppm after load stopped. Firmware service
timestamps tracked the same change within 0.22 ppm over each one-second interval.
The independent-generator measurements above help distinguish this from a
scope-only timebase change. These are relative measurements; they do not
identify a crystal, supply, temperature or grounding cause.

The cycle comparison counts actual MCO periods and interpolates only between
the adjacent physical clock edges. It uses the fixed nominal HSE/15 conversion
and one constant offset; it fits **no rate or local slope**. The 0.306 us maximum
residual therefore shows that the earlier long-window disagreement can arise
from a changing clock ratio, without lost firmware time. Synthetic regressions
still expose timestamp drift, delayed service edges, extra/missing clock edges
and incomplete coverage. The partial opening period cannot enter the comparison.

**Measurement practice:** distinguish elapsed-time accuracy against an external
reference from scheduling accuracy in the device's clock domain. A constant
clock-ratio fit alone can conflate them. Keep both results and their limits
visible; do not widen a timing gate or retrospectively relabel rejected captures.
Two complete native clock waveforms are published with lossless standard XZ
compression and original-byte hashes. Full wire/service records are published
for all five diagnostics; the other three clock waveforms are retained by hash,
and their reported clock metrics are not claimed as public waveform replay.

```sh
python3 examples/daisy/jack_session.py --clock-diagnostic \
  --port FIXTURE_PORT --scope-id SCOPE_ID --manifest BUILD/manifest.json \
  --out NEW_CAPTURE_DIRECTORY --max-seconds 3 --notes 'hardware clock diagnostic' \
  --audio-block 16 --audio-off-ms 2000 --dsp-voices 4 --dma-kib 4
python3 tools/inspect_daisy_clock.py --raw NEW_CAPTURE_DIRECTORY/fixture/raw.txt \
  --service NEW_CAPTURE_DIRECTORY/scope/digital_1_1.bin \
  --clock NEW_CAPTURE_DIRECTORY/scope/digital_2_0.bin \
  --dsp-reference build/test_daisy_dsp --out NEW_DIAGNOSTIC_REPORT.json
```

The clock inspector checks every interior full clock period, reports the first
gated partial period and the two boundary half-pulses separately, and compares frequency over identical physical
service intervals. It reports the existing service-timing rejection unchanged.
These first diagnostics cannot qualify jack response or substitute for the
audio-marker evidence absent from that firmware.

Firmware source `9fb130f` adds a separate diagnostic audio marker on **physical
pin 5 (PC8 / Daisy D4)**, requiring Saleae **digital input 5** on that pin.
Existing Saleae D4 remains on physical pin 4 for HSE/15. The official
[Seed3 pinout](https://daisy.nyc3.cdn.digitaloceanspaces.com/products/seed3/Seed3-Pinout.pdf)
identifies the physical pins. This build reserves PC8 as an output held low
outside measured `K` callbacks, including before and after acquisition; the
probe therefore never depends on a floating idle pin. Normal `J` mode and its
existing marker stay unchanged.

Five subsequent [simultaneous-clock/audio recordings](../../tests/measured/daisy/2026-10-20-jack-hse-audio)
verified this extension. Both bracketing normal-mode early finishes passed,
including the loaded finish with 4,285 independently observed callbacks and
1,427 verified DMA transfers. The three diagnostics retained all 32,000
acquisition observations and checked every audio pulse against counted HSE
cycles, using the existing callback bounds.

| Simultaneous diagnostic | Original global service residual | Residual against HSE cycles | Independently observed callbacks |
| --- | ---: | ---: | ---: |
| Unloaded, 3 seconds | 0.199 us | 0.197 us | 0; marker verified idle |
| Four DSP voices, 3 seconds, load stops at 2 seconds | 0.467 us | 0.289 us | 6,001 |
| Four voices + 4 KiB DMA, 10 seconds, load stops at 8 seconds | **12.620 us (rejected)** | 0.326 us | 24,007 |

The combined diagnostic verified all 7,999 DMA transfers and the complete DSP
sample signature. Its longest observed callback took 39.528 us; the longest
start-to-start interval was 334.768 us in HSE-cycle units for a nominal
333.333 us block period. No deadline, block-size, acquisition-overrun or ADC
failure was reported. Full native clock, service and audio waveforms plus wire
records are published for all three diagnostics, with lossless compression and
original-byte hashes; regression replay checks them all.

This fills the missing audio-marker evidence for the diagnostic mode. It does
**not** convert the combined run into a normal-mode timing pass or qualify jack
transitions under that workload. The changing relative clock ratio remains
visible, and its physical cause and absolute accuracy remain unresolved.
At this diagnostic stage, the 17 unattempted comparisons and one failed load
profile remained unqualified. The later M-mode results below supply separate
scheduling/behavior evidence. Portable headers and acceptance limits are unchanged.

Use `jack_session.py --clock-diagnostic --diagnostic-audio` only with the
supporting build and additional probe; old manifests are rejected for that
option. Pass `--audio NEW_CAPTURE_DIRECTORY/scope/digital_2_1.bin` to the clock
inspector. It checks every callback's count, duration, cadence and coverage in
counted HSE units with the existing audio bounds; the original service result
remains visible. This remains a diagnostic route, with no automatic conversion
into a passing jack qualification. No powered audio input is required.

Firmware source `08fcb82` provides an explicit **`M` clock-reference mode**
for the remaining DSP/DMA comparisons. It uses the same D4 hardware clock and
D5 audio wiring, accepts
the existing bounded faults, and has its own identity and `MSTART` record.
Normal `J` and diagnostic `K` identities remain separate; old images lack the
required manifest capability and cannot be selected accidentally. Runs remain
limited to ten seconds, with no artificial audio padding.

The reviewer produces two results:

- **Scheduling and behavior:** every complete HSE period is validated. Service,
  probe, presence and audio edges are compared in counted clock cycles using a
  fixed nominal conversion and a single constant offset. Service residual,
  adjacent-interval and pulse-width limits stay at 5/5/3 us. No rate is fitted.
  ADC aperture extrema and independent generator bounds remain on the original
  scope timeline; ambiguous voltage evidence is retained.
- **External clock stability:** the original whole-record scope/timebase fit,
  limits and failures remain visible. A scheduling pass does not turn a clock
  stability failure into an overall timing pass.

The combined report deliberately says “scheduling and behavior pass; clock
stability reported separately.” Synthetic regressions reject delayed work,
timestamp drift, missing/extra periods or service pulses, widened pulses,
missing audio callbacks and altered analog apertures. The previous measured
combined-load counterexample retains its external failure while satisfying
the separate scheduling checks.

All **18 remaining comparisons now pass scheduling and jack behavior** on
firmware source `08fcb82`: 14 load/baseline cases and four transition-fault cases.
The [complete measured replays](../../tests/measured/daisy/2026-10-20-jack-clock-reference)
retain 359,900 acquisition observations, 228,064 independently checked
audio callbacks and 97,740 verified SDRAM DMA transfers. Together with the five
original full passes, every planned profile has completed; the original failed
attempts retain their original labels and payloads.

| Comparison group | Cases | Observations | Separate external-clock failures |
| --- | ---: | ---: | ---: |
| Load profiles and final baseline | 14 | 280,000 | 9 |
| Insertion/removal ADC gaps and processing pauses | 4 | 79,900 | 4 |

Maximum service residual/adjacent-interval/width disagreement is
0.628/1.046/1.054 nominal us in counted HSE units, below the unchanged
5/5/3 us bounds. The deliberate 25 ms faults account for all 100 missed
acquisition slots and 100 excluded observations; the two pause
recoveries each invalidate their first observation after the gap. There were no
unrelated missed slots, hardware ADC failures, audio deadline violations or
DMA data errors.
Insertion/removal qualification and recovery passed during active DSP/DMA work.

The three 16-voice/16-KiB profiles verified 6,001 / 5,921 / 5,828 transfers
over their eight-second loaded intervals, with 1,997 / 2,078 / 2,171 skipped
launch opportunities at 16 / 48 / 96-frame blocks. They satisfy the existing
minimum-throughput and completion bounds, but do not sustain the requested
1 kHz launch rate. Outstanding transfers are never queued into catch-up bursts;
every launched transfer completed and its destination data was verified.

External-clock stability remains a separate unresolved result: **13 of 18**
records fail the original whole-record fit, with maximum residual 175.144 us.
These failures are not dropped or converted into overall timing passes. Relative
clock variation is measured; its physical cause and calibrated absolute
frequency remain unestablished.

Every published case includes full wire, generator and digital evidence, the
complete losslessly compressed native clock waveform, and conservative analog
aperture extrema. Regression tests reconstruct and review all 18 cases. Native
analog waveforms remain retained separately by hash. These are electrical-clamp
tests on one bare-board fixture, not mechanical cable coverage, a protected
production input, arbitrary DSP validation, codec fidelity or a long soak.
Portable library headers are unchanged.

Further inspection of the already-published 16-voice / 16-KiB / 16-frame
counterexample found a discrete period population that its mean frequency
concealed. Of 10,666,668 complete ungated output periods, **17,707 are short**
(mean 875.460 ns), versus 937.537 ns for the ordinary population. There are
no corresponding long periods under the diagnostic population boundary
(half a nominal 16 MHz source period away from the nominal output period).
All short events occur during the eight-second workload; none occur in the
two-second recovery interval. Their combined deficit is 1,098.548 us. The
unloaded baseline has no such events. This is consistent with discrete phase
advances near one source-clock cycle, rather than only smooth frequency drift.
It does **not** yet identify an oscillator, supply, coupling, divider or
measurement fault.

`tools/inspect_daisy_clock_periods.py` reports every contained full period,
including counts, extrema and a 1 ns histogram; it never removes a population
from acceptance. Its regression reuses the complete existing clock payload,
without adding another copy. This is a useful measurement precaution: inspect
individual periods as well as average frequency and whole-record phase error.
The original external timing rejection remains unchanged.

An additional independent-generator diagnostic on the shared sense node
was rejected for nine brief 5–9 ns excursions around probe transitions.
The [complete sense/probe/service waveforms and generator record](../../tests/measured/daisy/2026-10-20-clock-investigation)
are retained as a counterexample. The new independent-reference inspector
requires a unique nonuniform-timetable mapping, explains every occluded edge,
and checks the entire wired-AND waveform. It does not filter these extra
transitions into a pass.

The subsequent [five independent-reference comparisons](../../tests/measured/daisy/2026-10-20-independent-clock-reference)
observe the generator on its own 4.7 kΩ pulled-up node, disconnected from the
fixture sense input. Two preliminary recordings were rejected for 12 and 22
extra transitions. Three clean voltage snapshots did not establish reliability
over a full recording. A second, simultaneously recorded analog-derived digital
channel uses explicit 1.2/2.0 V hysteresis; both receivers have pulse filtering
disabled. All 320 edges on that channel pass the unchanged complete-sequence
and whole-record timing checks. The raw digital probe still fails in four of
the five comparisons; those failures remain visible.

| Workload | Generator vs scope, maximum fit residual | Fixture service vs scope, maximum fit residual | Short clock periods during first eight seconds |
|---|---:|---:|---:|
| Idle before | 0.334 µs | 0.260 µs | 0 |
| DMA only, 16 KiB | 0.307 µs | 1.716 µs | 137 |
| DSP only, 16 voices | 0.316 µs | 2.157 µs | 172 |
| Combined DSP/DMA | 0.330 µs | **181.108 µs** | **17,949** |
| Idle after | 0.317 µs | 0.210 µs | 0 |

No short periods occur in the measured two-second recovery portions. The
combined-load short-period deficit is 1,112.348 µs, and the independent
generator compared with counted fixture-clock time also fails its global fit
(133.599 µs). This narrows the disagreement to behavior associated with the
loaded fixture; it does not identify the oscillator, supply, divider, coupling
or measurement path responsible. Counted-clock scheduling passes throughout
100,000 observations, with no missed acquisitions or hardware ADC errors;
72,021 callbacks and 14,001 DMA transfers pass their checks.

The compact public payload includes complete generator records, both reference
receiver waveforms, two rejected attempts and three 500 MS/s voltage snapshots.
Regression tests replay every reference edge and preserve each receiver's
result. Complete native fixture clock/service/analog recordings are retained
separately by hash; their published summaries are **not** complete public
waveform replays. Firmware and portable headers are unchanged. A useful next
isolation is internal-RAM versus SDRAM DMA under the same DSP workload, with
transfer throughput measured rather than assumed equal.

Protocol 7 adds that comparison; the measured results follow below. Both
buffer pairs coexist in one image. `--dma-region 0` selects SDRAM and
`--dma-region 1` selects AXI SRAM; `--dma-period-us 1000` or `2000` selects the
requested launch interval. DSP voices, FIR/delay storage, audio block size,
interrupt priorities, cache ownership and full destination verification remain
the same. This compares the complete memory workload, including CPU cache and
verification costs; it cannot isolate DMA bus traffic alone.

The pinned SDK normally places writable globals in DTCM, which DMA2 cannot
access. A small [linker supplement](../../examples/daisy/dma_internal.lds) places
the internal pair in application AXI SRAM, excluding the bootloader's upper
32 KiB. Link-time assertions and inspection of the final ELF independently
check the 32 KiB pair, alignment and address bounds. The build manifest records
both pairs' addresses. A checksummed `JMEM` record reports the selected pair;
capture rejects a different address, overlapping buffers, a wrong region, or
an inconsistent cadence. Old protocol 1–6 recordings remain replayable.
GNU ld reports a forward `SRAM` region declaration because its `INSERT`
supplement must precede the SDK script; the final placement checks remain
mandatory. See the [GNU ld ordering rule](https://sourceware.org/binutils/docs/ld/Miscellaneous-Commands.html)
and ST's [DMA memory/cache example notes](https://github.com/STMicroelectronics/STM32CubeH7/blob/master/Projects/STM32H745I-DISCO/Examples/PWR/PWR_Domain3SystemControl/readme.txt).

The [twelve-case plan](../../examples/daisy/dma_comparison.py) brackets eight
combined-load runs with idle and DSP-only controls. It repeats the memory pairs
in reversed order at 1 ms and 2 ms, using 16 voices, 16-frame blocks and 16 KiB
copies. Each ten-second capture has eight loaded seconds and two recovery
seconds. Coverage requires at least half the requested launch rate (500 or
250 transfers/s), no gap over 10 ms, and complete data verification. This is a
minimum acceptance gate, not evidence of equal throughput. Pair reports retain
actual payload rates, skipped launches, callback counts and loaded durations;
unequal achieved work is explicitly marked as a confound. The slower pair tests
whether both regions can sustain the same requested rate.

### Internal RAM versus SDRAM: measured comparison

On 2026-10-20, protocol-7 source `0cc9d0d64642e9b2d53270421bc0469e59f5f5ec`
completed three early-finish checks and the twelve-case plan above. The
[complete digital and serial traces](../../tests/measured/daisy/2026-10-20-dma-memory/campaign.json)
retain all 249,826 observations. Across the full ten-second comparisons,
240,070 audio callbacks and 43,959 DMA transfers passed timing/data checks;
early finishes retained another 9,832 callbacks and 2,862 verified transfers.
No acquisition slots were missed and no ADC, audio deadline or DMA data errors
were reported. Maximum counted-clock service residual/interval/width errors
were 0.762/0.884/0.997 µs, within the unchanged 5/5/3 µs bounds.

| Memory and requested cadence | Verified transfers per eight-second load, two repeats | Skipped launches | External service-fit residual, two repeats |
| --- | --- | --- | --- |
| SDRAM, 1 ms | 5,984 / 5,981 | 2,014 / 2,018 | 1.576 / 1.110 µs |
| AXI SRAM, 1 ms | 7,999 / 7,999 | 0 / 0 | 0.849 / 0.614 µs |
| SDRAM, 2 ms | 3,999 / 3,999 | 0 / 0 | 1.270 / 1.006 µs |
| AXI SRAM, 2 ms | 3,999 / 3,999 | 0 / 0 | 0.712 / 0.817 µs |

All combined runs executed the same 384,112 DSP frames and 24,007 audio
callbacks. AXI SRAM sustained the requested 1 ms cadence; SDRAM delivered about
748 verified transfers/s. The 1 ms pairs therefore compare unequal achieved DMA
work. Both 2 ms pairs matched at 3,999 transfers, with no skipped launches.
These results include source generation, cache maintenance and full destination
verification; they are not raw-memory bandwidth benchmarks.

All twelve external service fits passed the original 5 µs bound, including
SDRAM. The previous approximately 181 µs anomaly did **not** reproduce, so this
batch does not establish an internal-RAM clock fix. Rare short HSE/15 periods
remain: 48–101 during each loaded combined run, none during its measured
recovery tail. DSP-only controls had 67/57; idle controls had none. Every period
remains in the timing review. All 768 independently generated edges passed on
the separately recorded hysteretic receiver, with maximum residual 0.336 µs.
Raw D0 retained 68–88 edges per recording instead of 64; all twelve raw-receiver
rejections remain explicit and are not converted into passes.

The comparison uses one image for both memory choices, but that image differs
from the earlier failing build. [ELF symbol inspection](../../tests/measured/daisy/2026-10-20-dma-memory/layout-comparison.json) shows that its SDRAM copy pair
moved from `0xc1d77400`/`0xc1d7b400` to `0xc0000000`/`0xc0004000`, and DSP delay
storage moved from `0xc0000000` to `0xc0008000`. Code layout also changed. These
are confounds for an old-versus-new comparison, not evidence of a physical
cause. The controlled firmware comparison below tests build dependence;
fixed-address SDRAM layout controls remain the next isolation step. No portable detector policy or timing limit changed as a result of this
batch. The practical findings are to verify DMA-visible placement in the final
ELF and compare completed work, not just requested rates.

Neither oscillator is an absolute calibration reference. The instrument's
published [MSO specifications](https://www.saleae.com/logic-mso) distinguish
time resolution from timebase accuracy and specify warmup conditions. A
constant scale fit handles relative frequency offset, but cannot excuse
time-varying phase error. ST's
[oscillator design guidance, section 7](https://www.st.com/resource/en/application_note/an2867-guidelines-for-oscillator-design-on-stm8afals-and-stm32-mcusmpus-stmicroelectronics.pdf)
identifies supply decoupling and separation from fast signals as relevant
design considerations; these are investigation hypotheses, not a diagnosis
of this fixture.

### Controlled firmware comparison: current, previous, current

A subsequent eighteen-capture experiment on 2026-10-20 restored the **exact
archived binaries**, with identities checked before and after each stage.
Current source `0cc9d0d64642e9b2d53270421bc0469e59f5f5ec` bracketed previous
source `08fcb8204e917cf8af8d1601710e56e765b9f59b`. No firmware was rebuilt.
[Complete serial and digital evidence](../../tests/measured/daisy/2026-10-20-firmware-comparison/campaign.json)
retains every clock period and both reference receivers, including failures.

Each stage used 60 seconds of idle settling, then the same six ten-second
captures: idle, DMA-only, DSP-only, two combined-load repeats, idle. Combined
load used 16 DSP voices, 16-frame callbacks and 16 KiB SDRAM copies requested
every 1 ms, with load ending at eight seconds. Wiring, receiver thresholds,
reference pulse sequence, capture code and host DSP reference were unchanged.
Both builds use the same compiler/SDK and DSP, acquisition and detector kernels.

| Stage | External service-fit residual, two combined repeats | Verified DMA transfers | Short HSE/15 periods during load |
| --- | --- | --- | --- |
| Current, before rollback | 1.286 / 1.299 µs | 5,984 / 5,986 | 100 / 108 |
| Previous image | 205.042 / 201.552 µs | 6,001 / 6,002 | 20,168 / 19,936 |
| Current, restored | 1.362 / 1.388 µs | 5,984 / 5,982 | 100 / 100 |

The large discrepancy returns with the previous image and disappears after
restoring the current image. This establishes **reversible build dependence on
this fixture and workload**. It does not identify an oscillator defect, electrical
coupling, instrument behavior, or which firmware-layout difference causes it.
All short-period observations remain in the analysis; none occurred in the
measured two-second recovery tails. The previous image's other four external
fits pass, as do all twelve current-image fits.

All 360,000 observations pass counted-clock scheduling, with maximum
residual/interval/width errors of
0.786/1.017/1.059 µs against unchanged 5/5/3 µs bounds.
All 288,084 audio callbacks pass the independent marker review and
59,936 DMA transfers pass full data verification. No missed acquisition
slots, ADC errors, audio deadline errors or DMA data errors were reported.
Each combined run executes 384,112 DSP frames and 24,007 callbacks. DMA
completion counts differ slightly, so identical requested settings still do
not establish identical bus traffic or CPU maintenance work.

All 1,152 generator edges pass on the separately recorded hysteretic
receiver (maximum residual 0.350 µs). Raw D0 has extra edges in
17 of eighteen recordings; those receiver failures remain explicit. The second
previous-image combined run has a passing raw D0 reference too, while retaining
its 201.552 µs clock failure. This is
relative timing evidence, not an absolute frequency calibration.

### Fixed SDRAM buffer placement in one image

The seventeen-record follow-up (three early finishes and fourteen comparisons)
completed on 2026-10-20 using source `839df1d7e53d9dc4461368f742f6b76136e0d2db`.
Protocol 8 reserves
both DMA pairs in **one firmware image**, selected at runtime with
`--dma-region 0` (low SDRAM) or `--dma-region 2` (high SDRAM). Region 1 remains
AXI SRAM. The source/destination pairs are `0xc0000000` / `0xc0004000` and
`0xc1d77400` / `0xc1d7b400`. The 2 MiB DSP delay stays at `0xc0008000`;
the 28,800,000-byte trace buffer moves to `0xc2000000` to avoid overlapping
the high pair. All four allocations coexist, so changing the runtime choice
moves neither executable code nor any other storage. Linker assertions reject
wrong sizes, overlaps, overflow and unaccounted SDRAM allocations. The builder
independently checks final ELF symbols; captures check reported DMA addresses
against that exact image's manifest.

The [fourteen-capture plan](../../examples/daisy/dma_placement.py) brackets
DMA-only and combined-load comparisons with idle/DSP controls. Combined runs
use low/high/high/low order at 1 ms and high/low/low/high order at 2 ms,
with the same 16 voices, 16-frame callbacks, 16 KiB transfers, eight-second
load and two-second recovery as before. Every transfer is verified; completion
counts and skipped requests remain explicit because identical requested rates
can produce different achieved work. Three early-stop checks precede the plan.
All captures are complete; the
[full serial and digital evidence](../../tests/measured/daisy/2026-10-20-sdram-placement/campaign.json)
includes every clock period and the failed raw reference receiver records.
The [complete replay](../../tests/test_daisy_dma_placement_measured.py) independently
checks the data and retains all four external clock failures.

| Requested DMA cadence | Low-address external residuals | High-address external residuals | Verified copies per run |
| --- | --- | --- | --- |
| 1 ms | 2.440 / 2.089 µs | 167.619 / 168.666 µs | Low: 5,986 / 5,983; high: 5,982 / 5,982 |
| 2 ms | 1.556 / 1.628 µs | 108.048 / 105.366 µs | 3,999 each at both addresses |

The large discrepancy follows the high pair in both orders and disappears
when returning to the low pair. At 2 ms, **every run completes exactly 3,999
transfers with no skips**, 384,112 DSP frames and 24,007 callbacks. That result
cannot be explained by unequal completed-transfer counts. Equal counts do not
imply identical bus timing, cache maintenance cost or electrical activity.
The 1 ms runs retain their 2,013–2,017 skipped launches as a throughput confound.
DMA-only controls at both addresses pass, each completing 7,999 transfers with
no skips. Initial/final idle and DSP-only controls pass too.

Under combined load, the high pair records 16,672–16,772 short HSE/15 periods
at 1 ms and 10,583–10,649 at 2 ms; the low pair records 134–206.
All fourteen measured recovery tails contain zero short periods. Every one of
the 289,007 observations, including 9,007 early-stop observations, passes
counted-clock scheduling. Its maximum residual/interval/width errors are
0.723/1.021/1.060 µs under unchanged 5/5/3 µs bounds. Full comparisons verify
288,084 audio callbacks and 55,927 DMA transfers, with zero missed acquisition
slots, ADC failures, audio deadline errors or corrupted DMA data.
All 896 separately recorded hysteretic reference edges pass (worst residual
0.333 µs). Raw D0 records extra edges in all fourteen comparisons; those
receiver failures remain failures and are not replaced with filtered data.

This establishes **DMA-address-dependent timing disagreement under combined
load on this fixture, with code and other storage held fixed**. It does not
identify an oscillator defect, SDRAM fault or instrument mechanism. A useful
next isolation is address alignment/row offset, followed by analog clock
confirmation to localize the physical effect. These results do not justify a
portable recommendation to place DMA buffers at low addresses.

The trace buffer moved relative to the earlier images to avoid overlap with
the high pair; this experiment does not recreate every detail of the old layout.
The reusable practices are to record actual linked/runtime buffer addresses,
compare achieved work, keep code/storage fixed across runtime selections, and
retain independent clock-stability checks even when internal scheduling passes.

### Fixed-storage buffer alignment comparison

Protocol 9 adds runtime-selectable views into two reserved 64 KiB SDRAM areas:
`0xc0210000` (low) and `0xc1d70000` (high). Both use byte offsets
`0`, `32`, `1024` and `0x7400`. Every source/destination remains a disjoint
16 KiB block of complete 32-byte cache lines, preserving the cache-ownership
rules described in [ST AN4839](https://www.st.com/resource/en/application_note/an4839-level-1-cache-on-stm32f7-series-and-stm32h7-series-stmicroelectronics.pdf).
These are address-offset controls, not a claim that a specific SDRAM row or
bank boundary has been isolated.

| Offset | Low selector / source | High selector / source |
| --- | --- | --- |
| 0 | 3 / `0xc0210000` | 4 / `0xc1d70000` |
| 32 | 5 / `0xc0210020` | 6 / `0xc1d70020` |
| 1024 | 7 / `0xc0210400` | 8 / `0xc1d70400` |
| `0x7400` | 9 / `0xc0217400` | 2 / `0xc1d77400` |

Destination is source + `0x4000`. Selector 0 retains the original low pair
at `0xc0000000` / `0xc0004000`; selector 1 retains AXI SRAM. The original low
pair has no offset headroom before DSP storage, so its two combined-load
controls bracket the alignment runs. DSP delay stays at `0xc0008000` and trace
storage at `0xc2000000`, unchanged from protocol 8. All choices coexist in one
image; code and every other allocation stay fixed between selections. Building
protocol 9 changes executable code relative to protocol 8, so the original
address controls must be remeasured before extending the earlier conclusion.

The [bounded plan](../../examples/daisy/dma_alignment.py) has thirty ten-second
comparisons: idle/DSP controls before and after, two original-low controls,
eight DMA-only selections, and sixteen combined runs (all eight selections,
then reverse order). Combined runs retain 16 voices, 16-frame callbacks,
16 KiB copies, eight seconds of load and two seconds of recovery. The requested
DMA period is 2 ms, where the previous experiment achieved matched work without
skips. Count matching is still measured, never assumed. Three early-finish
checks precede this plan. All three checks and thirty comparisons completed on
2026-10-20 using source `4a6f288f4cc723917bc06e95f1346a0f174ad283`, protocol 9
build `efb2237905e88d4bbaba81f8`.
The [complete serial/digital records](../../tests/measured/daisy/2026-10-20-sdram-alignment/campaign.json)
and [independent replay](../../tests/test_daisy_dma_alignment_measured.py) preserve
every clock period and all measured receiver/clock failures.

| Byte offset | Low-range residual, forward / reverse | High-range residual, forward / reverse |
| --- | --- | --- |
| 0 | 1.873 / 1.792 µs | 105.190 / 104.911 µs |
| 32 | 2.021 / 1.637 µs | 105.727 / 107.913 µs |
| 1024 | 1.747 / 1.831 µs | 103.808 / 104.113 µs |
| `0x7400` | 1.996 / 1.970 µs | 106.560 / 105.439 µs |

All eight combined runs in the high range fail the unchanged external clock
check; all eight in the low range pass. The original-low controls also pass
(2.213 / 1.682 µs), while the original-high address (`0xc1d77400`)
still fails in both orders. This reproduces the previous image's address
contrast despite the executable change. **The disagreement follows the tested
address range across all four offsets and both sweep directions.** None of
these offset changes fixes it. This does not isolate a physical SDRAM row/bank,
cache, power, oscillator or measurement-receiver mechanism.

Every active-DMA comparison completes exactly 3,999 fully verified 16 KiB
copies with zero skips. Every combined run executes 384,112 DSP frames and
24,007 audio callbacks. All 24 achieved-work comparisons match. These counts
remove unequal completed work as an explanation for this experiment; they do
not prove identical bus timing or electrical activity. All eight DMA-only
placements pass the external clock check, as do the initial/final idle and
DSP-only controls. DMA-only requests here are 2 ms, unlike the 1 ms DMA-only
controls in the preceding placement experiment.

All 609,406 observations, including 9,406 early-stop observations, pass
counted-clock scheduling. Maximum residual/interval/width errors are
0.801/1.013/1.051 µs under unchanged 5/5/3 µs bounds.
The full comparisons verify 672,196 audio callbacks and 103,974 DMA copies,
with no missed acquisition slots, ADC errors, audio deadline errors or data
corruption. All thirty recovery tails contain zero short HSE/15 periods.
All 1,920 separate hysteretic reference edges pass (maximum residual
0.365 µs). Raw D0 records extra edges in all thirty comparisons;
these remain receiver failures, without trimming or filtering the raw data.
Native analog and instrument sessions are retained separately by hash.

The next useful distinction is an analog observation of the clock output
under the same low/high workloads, keeping an independent reference and checking
the probe/receiver path. Another offset sweep alone is unlikely to localize the
physical cause. This remains a fixture-specific timing investigation; it changes
no portable detector policy and establishes no absolute frequency or audible
codec-quality qualification.

The follow-up analog protocol uses the same protocol-9 binary and the matching
zero-offset low/high views (selectors 3 and 4). “Low/high” refers to address
ranges; both run the same 16-voice DSP, 16-frame audio callbacks and 16 KiB DMA
copies requested every 2 ms. The finite plan in
[`clock_waveform.py`](../../examples/daisy/clock_waveform.py) contains six complete
receiver comparisons, four loaded voltage windows in low/high/high/low order,
two recovery windows, and four reserved repetitions after a deliberate probe-path
swap. The swap is a separate bench action, never an automatic assumption.

The receiver comparisons retain raw clock edges at 1.0, 1.65 and 2.3 V thresholds
alongside a separate scope-derived 1.2/2.0 V hysteretic receiver. Changing the
clock probe port also changes its audio-marker threshold; the independent
reference port stays at 1.65 V. No pulse filter is enabled. Short voltage windows
use an independent generator edge as an analog trigger, 1 GS/s native sampling,
10 ms before and 40 ms after the trigger. The fixture still runs its entire
10-second workload, including the two-second recovery tail. Its complete log and
achieved-work counts must be checked; a short external window does not provide
full-run scheduling coverage. Probe attenuation, grounds and channel assignments
must be recorded, with a baseline before adding the clock probe.

[`inspect_daisy_clock_waveform.py`](../../tools/inspect_daisy_clock_waveform.py)
retains all analog threshold crossings and unmatched digital edges. It reports
voltage extrema, transition times, short/long period populations and receiver
path delays. Interpolation cannot recover details below the sampling rate or
probe bandwidth. A waveform at the MCO output includes the output and measurement
paths; it does not isolate the underlying oscillator.

All sixteen planned captures are complete. The
[diagnostic reports](../../tests/measured/daisy/2026-10-20-clock-waveform/summary.json)
retain the receiver failures separately from valid clock observations. The
ten 50 ms voltage windows gave these short-cycle counts at 1.65 V; both digital
receivers agree with the analog counts and match every interior rising edge:

| Clock analog path | Low-address load, two runs | High-address load, two runs | Recovery, low/high |
| --- | --- | --- | --- |
| Original CH2 probe/input | 1, 1 | 88, 72 | 0, 0 |
| Swapped CH1 probe/input | 1, 3 | 64, 68 | Not repeated |

Ordinary cycles are approximately 937–938 ns; the short population concentrates
near 875 ns. The contrast survives changing the analog probe and input together.
That rules out an effect confined to the original analog path; it does not
isolate oscillator, output buffer, power integrity, board coupling or a shared
instrument effect. The absolute counts are observations, not acceptance limits.
All threshold crossings remain in the reports, including extra crossings at
1.2/2.0 V in some high-address records.

The six complete receiver comparisons show low-address external-fit residuals
of 1.774–2.154 µs and high-address residuals of 109.887–112.302 µs through valid
receivers. At a 1.0 V raw threshold, the clock receiver adds two edges in the low
case and four in the high case, failing strict waveform acceptance. The separate
hysteretic clock remains valid. The high-case audio-marker count also fails at
that shared raw threshold; this is an unqualified audio measurement, not proof
of a firmware callback error. Raw failures are never filtered into passes.

All sixteen runs complete identical work: 3,999 verified DMA copies, 384,112 DSP
frames and 24,007 audio callbacks each. In total there are 320,000 observations,
63,984 DMA copies, 6,145,792 DSP frames and 384,112 callbacks, with no missed
acquisition slots, ADC errors or DMA skips. Six complete external records and ten
short voltage windows have different coverage; the latter do not qualify the
remaining 9.95 seconds externally. The two unchanged-wiring baselines preceding
this sixteen-capture plan are excluded from those totals.

The original streamed clock analog clipped at a 5 V span. The triggered records
use a 10 V clock span and 5 V reference span. `scope_configuration` now keeps the
wider span on the explicitly selected `clock_scope_index` (default 1; use 0
after the swap); `clock_span_v=5.0` can reproduce the original setting. Reported
extrema across the ten windows are about −1.97 to +5.49 V. These include probe
and ground-lead response; the original clock probe used a clip ground. They do
not establish those excursions at the board pin or resolve true edge times
below probe/instrument bandwidth.

Native voltage samples, digital timelines, firmware logs and instrument sessions
are retained separately by hash. The linked reports and
[digest inventory](../../tests/measured/daisy/2026-10-20-clock-waveform/native-digests.json) are
compact published findings, not a standalone replay corpus for the raw analog
waveforms. No portable detector policy, absolute clock accuracy or audible codec
quality is qualified by this experiment. A useful next physical comparison is
the same low/high pair with a short ground spring or equivalent low-inductance
connection, before interpreting the observed ringing as a board defect.

The optional native-waveform analysis requires NumPy; the portable library and
standard host tests do not. Run its separate synthetic checks in an environment
with NumPy installed:

```sh
python3 tests/test_daisy_clock_waveform.py
python3 tools/inspect_daisy_clock_waveform.py --analog CAPTURE/analog_1.bin \
  --digital CAPTURE/digital_2_0.bin --derived CAPTURE/digital_1.bin \
  --out NEW_WAVEFORM_REVIEW.json
```

The capture modes and full-rate analog-trigger restriction follow Saleae's
[headless MSO API example](https://discuss.saleae.com/t/headless-logic2-automartion-support-for-logic-mso/3798).
Settings are saved explicitly because that preview warns that saved sessions may
not display all automation settings accurately in the GUI.

Do not treat passing results at one placement as a portable detector-policy
fix. Retain exact binaries and linker placement, then bracket a suspected
regression with a restoration test before attributing
it to source-level behavior or hardware.

```sh
python3 examples/daisy/jack_dsp_matrix.py --clock-reference --stage sweep \
  --case SELECTED_CASES --port FIXTURE_PORT --generator-port GENERATOR_PORT \
  --scope-id SCOPE_ID --manifest BUILD/manifest.json \
  --generator-manifest GENERATOR_BUILD/manifest.json \
  --dsp-reference build/test_daisy_dsp --out NEW_CAPTURE_DIRECTORY
```
