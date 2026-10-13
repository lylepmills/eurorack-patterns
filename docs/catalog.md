# Eurorack micro-pattern catalog

Research snapshot: 13 October 2026. A catalog of 66 small design choices that can make a module feel predictable while patching, playing, editing and recovering from mistakes. The emphasis is on reusable behavior rather than synthesis algorithms.

The strongest common principle is to separate **what the user or signal is doing** from **when it is safe and musically appropriate to act on it**. Jack presence, gate edges, knob movement, clock acquisition and preset loading need different policies. A blanket “debounce everything” or “smooth everything” rule breaks useful behavior.

Each entry identifies **Code**, **Manual**, **Maker account**, or **Release notes** evidence. Observed behavior belongs to the cited product/version; reuse ideas and checks are proposed applications. The checks are a test backlog, not results from a hardware evaluation. Numeric constants are examples tied to their original scan rates and circuitry. This is a curated first pass, not an exhaustive survey of available modules.

## Start with these shared contracts

These are candidates for reusable contracts. See [coverage](coverage.md) for the current code and remaining integration work.

| Contract | What it prevents | Entries |
| --- | --- | --- |
| Stable presence detection with explicit startup behavior | Routing changes during partial insertion | A01–A03 |
| Fast gate capture separate from presence/button filtering | Missed pulses and repeated notes | A04–A06 |
| Per-control filtering with guaranteed endpoints | Sluggish modulation, unreachable zero/full scale | B01–B05 |
| One owner for each button/knob gesture | A modifier edit also triggering a hold or release action | C04–C08 |
| Deliberate pickup plus visible stored and effective state | Jumps and controls that appear disconnected from the sound | C05–C06, D01–D02 |
| Explicit CV/gate/reset ordering | Wrong first notes and off-by-one sequences | E01–E06 |
| Bounded transitions and background work | Clicks, stalled fades, dropped events | F01–F10 |
| Separate user data, calibration and recovery domains | Lost patches, silent miscalibration, unrecoverable startup | G01–G08 |

## Browse by problem

- [Jack presence and trigger capture](#jack-presence-and-trigger-capture) — A01–A06
- [Analogue acquisition and filtering](#analogue-acquisition-and-filtering) — B01–B06
- [Knobs and gestures](#knobs-and-gestures) — C01–C11
- [Visible state and reversible actions](#visible-state-and-reversible-actions) — D01–D10
- [Musical timing and synchronization](#musical-timing-and-synchronization) — E01–E12
- [Audio transitions and runtime isolation](#audio-transitions-and-runtime-isolation) — F01–F10
- [Startup storage and recovery](#startup-storage-and-recovery) — G01–G08
- [Electrical boundaries](#electrical-boundaries) — H01–H03

## What the Beads jack detector actually does

Beads tests the expected probe sequence in 64-decision windows. A window with at most two mismatches counts as unpatched and immediately clears the bad-window streak; eight bad windows establish patched state. Initialization deliberately starts as patched and seeds a bad first window. [Decision and initialization](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/normalization_detector.cc#L38-L81), [constants](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/normalization_detector.h#L88-L100).

At 48 kHz, the 4 kHz block callback and prescaler of two give a nominal 32 ms window and 256 ms for eight windows. Boundary alignment affects actual recognition time. That is a **presence policy**, not a gate-trigger delay. Reuse its reasoning, then choose timing and startup behavior for the new circuit. [Callback](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/beads.cc#L118-L122), [prescaler](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/beads.cc#L289-L293), [block rate](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/beads.cc#L50).

## Jack presence and trigger capture

### A01 Preserve normalization through tentative insertion

*Code.* **Observed:** Beads accepts a window with ≤2 probe mismatches as normalized/unpatched; a clean window immediately clears the bad-window streak. Eight consecutive bad windows are required to become unnormalized/patched. **Reuse:** treat jack-presence confidence separately from signal value. **Tradeoff/test:** slower insertion recognition; replay partial insertion, bounce, genuine disconnect, silent patched source, and correlated input. Do not apply this delay to musical gate edges. [Decision logic](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/normalization_detector.cc#L61-L81), [constants](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/normalization_detector.h#L88-L100).

### A02 Test the first cable between separate cases

*Maker account.* A-152's clock-presence method uses the socket ground contact; Doepfer documents failure with an external clock until a second cable establishes ground. **Reuse:** cable presence must not rely on an unrelated pre-existing ground path. Test same-case, separately powered case, and a desktop sequencer with exactly one cable. [A-152 technical note](https://doepfer.de/a152.htm).

### A03 Make the common patch work with one cable

*Manual.* **Noise Engineering Desmodus Versio.** **Observed:** unpatched right input receives the left signal. **Reuse:** provide a predictable mono-to-stereo default. **Caveat:** document which jack breaks normalization; do not mistake silence for unplugging. **Test:** left-only, right-only, stereo, silent connected source, and partial insertion. [Desmodus Versio manual](https://portal.noiseengineering.us/manuals/desmodus-versio/).

### A04 Separate gate-on and gate-off thresholds

*Code.* **Observed:** Plaits enters high above 0.3 and returns low below 0.1 in its normalized trigger domain. **Reuse:** Schmitt behavior prevents multiple events on noisy/slow edges. **Tradeoff/test:** thresholds must match actual electrical scaling; inject slow ramps, ringing, and marginal amplitudes. [Trigger Schmitt state](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/plaits/dsp/voice.cc#L102-L116).

### A05 Preserve brief events across slower processing domains

*Code.* **Observed:** Braids OR-latches detected triggers at the audio interrupt rate until a completed ADC scan consumes them; it separately stores sample-level sync flags. **Reuse:** carry edges, not merely the current logic level, across rate boundaries. **Tradeoff/test:** a boolean latch collapses multiple events; use a counter/queue where multiplicity matters. Test pulses shorter than the control period. [Trigger capture](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/braids/braids.cc#L102-L135).

### A06 Keep button debounce out of high-rate clock paths

*Maker account.* Doepfer's A-155 manual-step debounce modification limits maximum clock rate to a few hundred Hz. **Reuse:** different event producers should have different conditioning, even when they invoke the same musical action. Check rapid external clocks while repeatedly tapping the manual step button. [Doepfer DIY, 4.2.7](https://doepfer.de/DIY/a100_diy.htm).

## Analogue acquisition and filtering

### B01 Give each signal role its own filter budget

*Code.* **Observed:** Beads assigns pots a 0.05 one-pole coefficient; CV channels vary (pitch/density 1.0, time/size/shape 0.5, assign 0.1). **Reuse:** separate human-control denoising from CV bandwidth requirements. **Tradeoff/test:** coefficients only mean time constants at a stated update rate; measure step response, noise, and modulation attenuation per channel. [Channel setup](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/cv_reader.cc#L43-L85).

### B02 Read CV at useful resolution before attenuating it

*Maker account.* MI independently digitizes pot, attenuverter and CV; software attenuation preserves detail for small modulation amounts. **Reuse:** retain full signal acquisition precision, then scale. Check tiny modulation against large offsets, including true zero depth. [MI CV inputs, Advantages](https://pichenettes.github.io/mutable-instruments-documentation/tech_notes/cv_inputs/#advantages).

### B03 Make filtered controls reach both endpoints

*Maker account.* MI warns that threshold/backlash processing can strand pots short of minimum/maximum. **Reuse:** explicitly remap and clamp endpoints after adding movement thresholds. Check slow approaches to both stops; zero output and full feedback, depth or range must actually be reachable. [MI CV inputs, ADC input filtering](https://pichenettes.github.io/mutable-instruments-documentation/tech_notes/cv_inputs/#adc-input-filtering).

### B04 Budget acquisition time at the worst source impedance

*Maker account.* Thea Flowers explains ADC sample-capacitor settling and the pot's maximum source impedance near midpoint. **Reuse:** validate settling across mux channel jumps, not just static endpoints. Check alternating minimum/maximum channels with the pot at center; longer acquisition costs scan bandwidth. [SAM D21 ADC, Input impedance](https://blog.thea.codes/getting-the-most-out-of-the-samd21-adc/#input-impedance).

### B05 Treat averaging and calibration as different tools

*Maker account.* Flowers measures ADC errors, applies gain/offset calibration, then optionally interpolates a correction table. **Reuse:** averaging helps noise but does not substitute for scale accuracy. Check independent intermediate voltages after fitting; characterize settling and latency too. [SAM D21 ADC, Offset and gain error correction and Above and beyond](https://blog.thea.codes/getting-the-most-out-of-the-samd21-adc/#offset-gain-error-correction).

### B06 Keep input paths separately observable

*Maker account.* MI notes that separate acquisition makes pot, attenuverter and CV independently testable. **Reuse:** factory diagnostics should expose each raw input as well as the combined parameter, so a bad pot cannot masquerade as a CV fault. Check one deliberately fixed input at a time. [MI CV inputs, Advantages](https://pichenettes.github.io/mutable-instruments-documentation/tech_notes/cv_inputs/#advantages).

## Knobs and gestures

### C01 Make an attenuverter's zero easy to find

*Code.* **Observed:** Beads centers the raw pot at 0.5 and sets output to zero within ±0.03, with a shaped response outside. **Reuse:** give meaningful neutral positions a deliberate plateau. **Tradeoff/test:** sacrificed resolution near zero; sweep slowly through center with ADC noise and component tolerance. [Pot law](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/cv_reader.h#L108-L113).

### C02 Give important continuous values broad landing zones

*Code.* **Observed:** Beads' detune mapping has flat regions at chosen intervals and smoothstep transitions between them. **Reuse:** let users find unity, octave, common ratios, or zero by feel while retaining continuous movement. **Tradeoff/test:** a nonlinear travel-to-value relationship; verify monotonicity and usable fine adjustment in both directions. [Detune mapping](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/cv_reader.h#L114-L129).

### C03 Quantize with memory of the current bin

*Code.* **Observed:** Braids enlarges the active note's decision region using 9:7 weighted neighboring boundaries. **Reuse:** use stateful hysteresis for discrete selections instead of rounding noisy ADC values. **Tradeoff/test:** upward/downward thresholds differ; hold at every boundary with noise, then sweep both directions. [Quantizer](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/braids/quantizer.cc#L71-L104).

### C04 Require intentional motion before entering a hidden edit

*Code.* **Observed:** Beads locks the main parameter on modifier engagement, then waits for >0.03 pot motion before editing the hidden parameter. **Reuse:** pressing a modifier alone should not overwrite a stored secondary setting. **Tradeoff/test:** a small initial travel before takeover; test resting-hand jitter, modifier taps, and slow turns. [Hidden edit state](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/pot_controller.h#L72-L93), [movement threshold](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/pot_controller.h#L106-L124).

### C05 Rejoin the original parameter smoothly after a hidden edit

*Code.* **Observed:** Beads returns through relative catch-up: movement adjusts the stored main value with a bounded direction-dependent ratio until physical and stored positions meet. **Reuse:** avoid a parameter jump when a shared knob resumes its primary role. **Tradeoff/test:** temporary non-1:1 feel; test near endpoints and repeated enter/exit cycles. [Catch-up](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/pot_controller.h#L126-L144).

### C06 Guide soft takeover

*Manual.* **Befaco Oneiroi.** **Observed:** Catch mode waits for the knob to reach the parameter value; LEDs indicate direction and acknowledge capture. **Reuse:** prevent jumps after page changes or randomization. **Caveat:** define the pickup target under CV. **Test:** approach from both directions with noisy knobs and active modulation. (§15.1) [Oneiroi manual](https://befaco.org/docs/Oneiroi/Oneiroi_User_Manual.pdf).

### C07 Once movement is intentional, keep following small increments

*Code.* **Observed:** DLD starts a 250-update tracking window after a pot exceeds its change threshold; during that window it accepts smaller changes, refreshing on another large move. **Reuse:** distinguish idle noise rejection from active fine adjustment. **Tradeoff/test:** noise is temporarily passed while tracking; test small finishing movements after a fast turn and purely idle noise. [Adaptive movement tracking](https://github.com/4ms/DLD/blob/dfc4295fc9ca71be6243217ab544c2ef71705e3b/params.c#L230-L275).

### C08 Consume a gesture once its meaning is established

*Code.* **Observed:** Beads marks a long press as consumed so release does not generate a second action; editing gain while holding its modifier continually resets the long-press timer. **Reuse:** explicit gesture ownership prevents a knob-plus-button edit also invoking hold/release commands. **Tradeoff/test:** define gesture precedence; test release just before/after timeout and modifier use during a long hold. [Event handling](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/ui.cc#L89-L131).

### C09 Make gesture timing adjustable

*Manual.* **ALM Pamela’s PRO Workout.** **Observed:** encoder hold time is a setting. **Reuse:** accommodate different playing styles and dexterity. **Caveat:** keep a reliable distinction between press and hold. **Test:** very short/long settings, near-threshold releases, and repeated quick clicks. (§6.4) [Pamela’s PRO manual v0.4 / firmware131](https://assets.busycircuits.com/docs/alm034-manual.pdf).

### C10 Navigate laterally across channels

*Manual.* **ALM Pamela’s PRO Workout.** **Observed:** holding Start/Stop while turning the encoder moves between the same parameter on different outputs. **Reuse:** compare or balance channels without repeated menu traversal. **Caveat:** consume modifier presses so navigation cannot also stop transport. **Test:** all press/release orders while running. (§4.15) [Pamela’s PRO manual v0.4 / firmware131](https://assets.busycircuits.com/docs/alm034-manual.pdf).

### C11 Separate performance guards from preset content

*Manual.* **Xaoc Moskwa II.** **Observed:** CV-lock disables pitch knobs and is deliberately excluded from presets. **Reuse:** stop accidental pitch changes while editing nearby functions. **Caveat:** clearly define unlocking and power-cycle behavior. **Test:** lock, move knobs, load another preset, unlock; observe every transition. (p.9) [Moskwa II / Ostankino II manual, rev.1965/2.6](https://xaocdevices.com/manuals/xaoc_moskwa2_ostankino2_manual_A4.pdf).

## Visible state and reversible actions

### D01 Show the panel-selected state and CV-effective state separately

*Code.* **Observed:** Plaits gives the button-selected engine a pulsing indication and the CV-active engine a separate steady indication. **Reuse:** distinguish base setting from modulation result so external CV does not make the panel appear contradictory. **Tradeoff/test:** limited LED vocabulary; ask users to identify both under slow/fast modulation. [Selected versus active](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/plaits/ui.cc#L147-L166).

### D02 Show who owns each value

*Manual.* **Intellijel Metropolix.** **Observed:** Home Screen 3 displays loaded values with override dots where presets supersede panel controls. **Reuse:** expose physical/stored disagreement. **Caveat:** an override marker is different from a modulation indicator. **Test:** load conflicting knob and switch states, then reclaim each control. (printed p.30; PDF p.31) [Metropolix v1.6 manual](https://intellijel.com/downloads/manuals/metropolix_manual_v1.6_2025.09.24.pdf).

### D03 Encode important states with more than hue

*Code.* **Observed:** Plaits offers a color-blind mode with one hue and different LED brightness by bank. **Reuse:** give meaningful states a second readable cue. **Check:** identify each state with color unavailable, from typical playing distance and under bright light. Brightness alone also needs sufficient contrast. [LED rendering](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/plaits/ui.cc#L129-L136).

### D04 Make exploration reversible

*Manual.* **Befaco Oneiroi.** **Observed:** randomization has undo/redo through SHIFT+RANDOM. **Reuse:** let musicians compare adventurous changes safely. **Caveat:** specify which intervening edits invalidate undo. **Test:** randomize, manually edit, undo, redo; define and verify the intended undo boundary. (§13) [Oneiroi manual](https://befaco.org/docs/Oneiroi/Oneiroi_User_Manual.pdf).

### D05 Provide an explicit return to panel

*Manual.* **Befaco Oneiroi.** **Observed:** a gesture restores parameters to physical control positions. **Reuse:** recover a comprehensible starting point when hidden state diverges. **Caveat:** this can cause audible jumps; label it distinctly from factory reset. **Test:** invoke after randomization and secondary-page editing. (§13) [Oneiroi manual](https://befaco.org/docs/Oneiroi/Oneiroi_User_Manual.pdf).

### D06 Expose and cancel pending changes

*Manual.* **Intellijel Metropolix.** **Observed:** queued presets blink; reselecting cancels, another selection replaces, and loading confirms. Stopping also applies the queued load. **Reuse:** make quantized actions reversible until commitment. **Caveat:** define transport-stop behavior. **Test:** cancel, replace, and stop immediately before the boundary. (printed p.110; PDF p.111) [Metropolix v1.6 manual](https://intellijel.com/downloads/manuals/metropolix_manual_v1.6_2025.09.24.pdf).

### D07 Cancel arming without destroying existing material

*Manual.* **Instruō Lúbadh.** **Observed:** in Armed Input Monitoring mode, Erase disarms without deleting the loop. **Reuse:** make cancellation cheap and safe. **Caveat:** the same button erases in other states; distinguish arming visibly. **Test:** cancel just before record begins and after it begins. (p.20) [Lúbadh firmware-v2 manual](https://www.instruomodular.com/wp-content/uploads/2023/10/Lubadh-Manual-Firmare-V2-A5-.pdf).

### D08 Reset behavior independently from content

*Manual.* **Instruō Lúbadh.** **Observed:** Mode Reset restores default modes without deleting recorded buffers. **Reuse:** recover from confusing configuration while preserving creative work. **Caveat:** name reset scopes precisely. **Test:** record valuable material, alter every mode, reset, and compare buffers. (p.34) [Lúbadh firmware-v2 manual](https://www.instruomodular.com/wp-content/uploads/2023/10/Lubadh-Manual-Firmare-V2-A5-.pdf).

### D09 Offer a temporary map of current controls

*Manual.* **Expert Sleepers disting EX.** **Observed:** in single mode, holding V reveals input/knob functions; turning it shows outputs. Dual-mode help can be held open and disappears on release. **Reuse:** make unfamiliar patches self-explanatory without permanent screen clutter. **Caveat:** viewing must not change the sound. **Test:** open help during active modulation and release in another screen. (pp.15,19) [disting EX firmware1.26 manual](https://www.expert-sleepers.co.uk/downloads/manuals/disting_EX_user_manual_1.26.pdf).

### D10 Commit expensive changes explicitly

*Manual.* **Expert Sleepers disting EX.** **Observed:** selected slow parameters such as wavetables wait for an encoder confirmation. **Reuse:** let browsing remain responsive and avoid loading every intermediate choice. **Caveat:** ordinary continuous controls should stay immediate. **Test:** scroll many choices, confirm once, then change again during loading. (p.15) [disting EX firmware1.26 manual](https://www.expert-sleepers.co.uk/downloads/manuals/disting_EX_user_manual_1.26.pdf).

## Musical timing and synchronization

### E01 Allow a gate to arrive slightly before its CV

*Code.* **Observed:** Plaits delays trigger processing by 1 ms specifically for sequencers/interfaces whose CV follows gate. **Reuse:** make CV/gate acquisition order a deliberate contract. **Tradeoff/test:** added latency; test CV leading/lagging gate and rapid notes. [Trigger delay](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/plaits/dsp/voice.cc#L95-L100). o_C exposes selectable acquisition delays rather than one fixed value. [Quantermain settings](https://ornament-and-cri.me/user-manual-v1_3/).

### E02 Latch disruptive selection CV at the musical event

*Code.* **Observed:** Plaits captures engine CV at the trigger edge; without a trigger cable it follows continuously. **Reuse:** event-sample mode/algorithm choices that should remain consistent during a note. **Tradeoff/test:** ongoing CV changes become deferred; test modulation around the trigger boundary and patch/unpatch behavior. [Engine CV capture](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/plaits/dsp/voice.cc#L102-L124).

### E03 Give inferred events a refractory interval

*Code.* **Observed:** Rings inhibits retriggering after a strum, with four times the interval for audio-onset detection. **Reuse:** prevent one physical gesture/transient from producing several inferred events. **Tradeoff/test:** it can reject intentional flams/fast notes; choose by event source and test double attacks across the boundary. [Strummer](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/rings/dsp/strummer.h#L61-L88).

### E04 Define simultaneous event precedence

*Manual.* **Observed:** o_C Harrington 1200 handles reset before simultaneous chord transformations. **Reuse:** specify reset/clock/mode-change precedence, including whether reset emits step one or arms it. **Check:** move reset across the clock boundary by one processing interval; check pitches and gates, not just the cursor. [o_C v1.3, Harrington 1200](https://ornament-and-cri.me/user-manual-v1_3/).

### E05 Commit rhythmic edits at a musical boundary

*Manual.* **Observed:** Muxlicer applies address edits on the next clock and gate-mode edits on the next step. **Reuse:** keep pending and active rhythm settings separate. **Check:** change ratchet count during the final subdivision; avoid overdue bursts or a truncated next step. This waiting policy is unsuitable for some deliberate glitch gestures. [Muxlicer, PDF pp.4 and 6](https://befaco.org/docs/Muxlicer/Muxlicer_User%20Manual.pdf#page=4).

### E06 Separate clock acquisition from transport state

*Manual.* **Observed:** Pam PRO recommends a separate Run gate for presync/stop detection; its Reset-input mode needs at least two clock pulses to start. **Reuse:** distinguish transport, period acquisition and phase. **Check:** one pulse then silence, Run before/after clock, and clock while stopped; verify the first subdivision. [Pam PRO v0.4, pp.20 and 22–23](https://assets.busycircuits.com/docs/alm034-manual.pdf#page=20).

### E07 Choose clock smoothing for the musical job

*Code and manual.* **Observed:** DLD offers clock-period deadbands and averaging options with different tempo-response times. **Reuse:** stabilize a delay without discarding intentional tempo modulation. **Check:** random jitter, swing, drift and abrupt tempo changes; measure settling and missed/double events. Source contains experimental modes beyond the released choices. [DLD v5 notes](https://4mscompany.com/DLD/manual/V5-Release-Notes.pdf), [clock filters](https://github.com/4ms/DLD/blob/dfc4295fc9ca71be6243217ab544c2ef71705e3b/buttons_jacks.c#L175-L287).

### E08 Hold the last tempo until deliberate takeover

*Manual.* **Make Noise Mimeophon.** **Observed:** after clock disappears, established timing continues until Rate changes. **Reuse:** avoid surprising jumps during clock interruptions; support tap tempo. **Caveat:** this policy suits effects better than every transport. **Test:** missing pulses, stopped clock, cable removal, then knob movement. (p.13) [Mimeophon manual](https://www.makenoisemusic.com/wp-content/uploads/2024/03/mimeophon-manual.pdf). A different deliberate policy is QCD auto-stop: effects and trigger generators need not agree. [QCD v2, p.2](https://4mscompany.com/QCD/QCD-manual-v2.pdf#page=2).

### E09 Treat a clock restart as a distinct event

*Code.* **Observed:** Marbles recognizes a sufficiently long gap, resets train phase/counters, and raises a downstream reset instead of treating the gap as an ordinary period. **Reuse:** distinguish transport stop/restart from tempo change. **Tradeoff/test:** intentionally sparse clocks need a suitable timeout; test missing pulses and long rests. [Restart handling](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/marbles/ramp/ramp_extractor.cc#L185-L203).

### E10 Require sustained evidence before switching input interpretation

*Code.* **Observed:** Marbles switches to audio-rate clock processing only after consecutive qualifying pulses; the period threshold also has hysteresis. **Reuse:** protect automatic regime/mode detection from brief excursions. **Tradeoff/test:** delayed mode entry; test chirps and signals hovering at the boundary. [Regime detection](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/marbles/ramp/ramp_extractor.cc#L205-L217).

### E11 Earn estimator trust slowly; withdraw it quickly

*Code.* **Observed:** Marbles scores competing clock predictors with asymmetric smoothing: confidence rises slowly and falls quickly after error. **Reuse:** confidence-based automatic choices should abandon a broken assumption promptly. **Tradeoff/test:** possible estimator churn; test steady jitter, alternating intervals, and sudden tempo changes. [Predictor scoring](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/marbles/ramp/ramp_extractor.cc#L108-L167).

### E12 Keep trigger pulses separate at high rates

*Code.* **Observed:** In trigger mode, DLD limits clock-output high time to the lesser of half-period and its trigger-duration limit; gate mode uses half-period. **Reuse:** shorten nominally fixed pulses before they merge into a sustained gate. **Check:** sweep tempo and multiplication across the crossover, measuring both minimum high and low times against receiving modules. [DLD timer](https://github.com/4ms/DLD/blob/dfc4295fc9ca71be6243217ab544c2ef71705e3b/timekeeper.c#L49-L69).

## Audio transitions and runtime isolation

### F01 Let dependent detectors settle before unmuting

*Code.* **Observed:** after codec reconfiguration, Beads blanks output and suspends input-peak tracking and AGC timing for `kBlockRate / 4` blocks (250 ms); state-change monitoring also waits. **Reuse:** after sample-rate/codec changes, explicitly reacquire trustworthy input context before enabling derived behavior. **Tradeoff/test:** brief silence versus unstable gain/mode decisions; repeatedly switch rates with silent, loud, mono, and stereo inputs. [Blanking](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/beads.cc#L158-L175), [state monitor](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/beads.cc#L351-L355), [AGC timing](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/gain_control.cc#L113-L120), [peak tracking](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/beads/gain_control.cc#L148-L158).

### F02 Serialize transitions and keep the latest requested destination

*Code.* **Observed:** DLD starts a read-head fade when idle; requests during a fade replace a pending destination rather than restarting the current fade. **Reuse:** rapid control changes should not indefinitely interrupt a transition. **Tradeoff/test:** target latency and skipped intermediates; sweep rapidly during fades and confirm bounded completion. [Transition coordination](https://github.com/4ms/DLD/blob/dfc4295fc9ca71be6243217ab544c2ef71705e3b/looping_delay.c#L292-L375).

### F03 Keep enough tail to resume recording gracefully

*Code.* **Observed:** Clouds captures a short tail after freezing recording, then blends that continuation with live input when recording resumes. **Reuse:** preserve boundary context for freeze/hold/loop edits. **Tradeoff/test:** extra memory and a transitional blend; repeatedly freeze/unfreeze discontinuous and DC-offset material and inspect the seam. [WriteFade](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/clouds/dsp/audio_buffer.h#L126-L165).

### F04 Classify state changes by what really needs resetting

*Code.* **Observed:** Clouds distinguishes benign playback-mode changes from changes requiring buffer reinitialization; audio processing outputs silence while state is inconsistent. **Reuse:** preserve reusable state and gate access to invalid state during reconfiguration. **Tradeoff/test:** silence itself may need a ramp in another design; test every transition pair, especially frozen memory. [Mode preparation](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/clouds/dsp/granular_processor.cc#L370-L386), [output guard](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/clouds/dsp/granular_processor.cc#L159-L174).

### F05 Protect recorded material during exploration

*Manual.* **Make Noise Mimeophon.** **Observed:** HOLD manipulation is non-destructive; returning controls can recover the held repeats. **Reuse:** separate captured content from its playback transforms. **Caveat:** define what ends protection. **Test:** extreme transforms, reversal, and restoring controls before releasing HOLD. (p.14) [Mimeophon manual](https://www.makenoisemusic.com/wp-content/uploads/2024/03/mimeophon-manual.pdf).

### F06 Choose transition behavior by musical intent

*Manual.* **Make Noise Mimeophon.** **Observed:** free Rate produces continuous Doppler effects; clocked Rate crossfades between ratios without slew; microRate remains continuous. **Reuse:** separate rhythmic selection from expressive modulation. **Caveat:** universal smoothing destroys intentional pitch gestures. **Test:** fast CV near ratio boundaries in both modes. (pp.11–13) [Mimeophon manual](https://www.makenoisemusic.com/wp-content/uploads/2024/03/mimeophon-manual.pdf).

### F07 Capture events briefly and run their handlers later

*Code.* **Observed:** crow masks interrupts for queue operations, then runs handlers after re-enabling them; full queues reject new events and report overflow. **Reuse:** keep arbitrary UI/script work out of capture critical sections. **Check:** burst events into a deliberately slow consumer; verify deadlines and the drop policy. Enlarging a queue cannot fix sustained overload. [crow event queue](https://github.com/monome/crow/blob/b340579d94e57e2b43336611b2c4037cff74bb80/lib/events.c#L45-L86).

### F08 Rank interrupts by audible deadlines

*Code.* **Observed:** DLD places its sample clock above audio DMA, and parameter scanning below both. **Reuse:** document deadline priorities before adding USB/display work. **Check:** stress controls and storage while measuring audio deadlines and edge jitter. A long high-priority handler still starves the rest; copy the reasoning, not the numerical priorities. [Timer priorities](https://github.com/4ms/DLD/blob/dfc4295fc9ca71be6243217ab544c2ef71705e3b/timekeeper.c#L125-L172), [audio DMA](https://github.com/4ms/DLD/blob/dfc4295fc9ca71be6243217ab544c2ef71705e3b/i2s.c#L161-L170).

### F09 Save a coherent state without disrupting music

*Release notes.* **Observed:** Ansible fixed possible preset loss by disabling I²C during writes; disting EX v1.12 removed audio interruptions during saves. **Reuse:** serialize a stable snapshot and design explicitly around flash stalls and concurrent writers. **Check:** save while audio and external edits continue; reload a coherent result and measure any dropped-input interval. Neither change log proves transactional power-loss safety. [Ansible v3.1.0 notes within v3.1.1](https://github.com/monome/ansible/releases), [disting EX v1.12](https://www.expert-sleepers.co.uk/distingEXfirmwareupdates.html).

### F10 Keep the executing action stable during a scene switch

*Release notes.* **Observed:** Teletype fixed SCENE-related command corruption by caching commands in execution. **Reuse:** an action that replaces its own backing preset/program must retain valid state until completion. **Check:** switch scenes from inside an event callback; reject mixed old/new commands and stale references. Apply equivalent ownership rules to audio-state replacement. [Teletype v5 update notes](https://monome.org/docs/teletype/manual/).

## Startup storage and recovery

### G01 Give malformed user data a usable fallback

*Manual.* **Xaoc Moskwa II.** **Observed:** invalid custom scale files restore original quantization settings. **Reuse:** keep the instrument playable after a broken import. **Caveat:** silent fallback can hide a problem; add understandable feedback. **Test:** missing delimiters, illegal characters, truncated files, and an empty scale. (p.6) [Moskwa II / Ostankino II manual, rev.1965/2.6](https://xaocdevices.com/manuals/xaoc_moskwa2_ostankino2_manual_A4.pdf).

### G02 Explain degraded startup while remaining usable

*Manual.* **Observed:** disting reports missing/corrupt calibration and continues with defaults. **Reuse:** distinguish playable fallback from accurate calibrated operation. **Check:** erase or corrupt a calibration fixture, verify bounded defaults and an understandable notice, then recalibrate. Avoid making the notice an obstacle to performance. [disting mk4 v4.28, Startup p.6](https://www.expert-sleepers.co.uk/downloads/manuals/disting_user_manual_4.28.pdf#page=6).

### G03 Keep user resets separate from factory calibration

*Manual.* **Observed:** o_C app reset preserves calibration; settings saves are explicit, acknowledged, and briefly pause operation. **Reuse:** define independent reset domains and disclose any timing interruption. **Check:** reset/reboot without changing calibration; measure outputs during saves. Background saving needs a design that actually maintains deadlines. [o_C v1.3, Operational principles](https://ornament-and-cri.me/user-manual-v1_3/).

### G04 Migrate and validate persisted fields independently

*Code.* **Observed:** Castor & Pollux versions stored settings, supplies defaults for newly added fields, and bounds individual values; invalid critical calibration can reject the record. **Reuse:** preserve valid older preferences while handling absent/invalid fields deliberately. **Check:** load each shipped version and fuzz individual fields. Version markers and bounds alone do not establish atomic power-loss recovery. [Migration](https://github.com/wntrblm/Castor_and_Pollux/blob/652b28c950ed04ca41f0d8aa98d9b1be2f310f76/firmware/src/gem_settings_load_save.c#L59-L93), [validation](https://github.com/wntrblm/Castor_and_Pollux/blob/652b28c950ed04ca41f0d8aa98d9b1be2f310f76/firmware/src/gem_settings_load_save.c#L23-L57).

### G05 Panic must stop producers and clear outputs

*Manual.* **Observed:** Teletype documents KILL clearing triggers and stopping its metronome. **Reuse:** specify a complete panic, including pending events that could reassert outputs. **Check:** panic with high gates, delayed triggers and periodic producers; outputs should remain quiescent until restart. The broader cancellation requirement is our proposed contract. [Teletype manual, KILL and update notes](https://monome.org/docs/teletype/manual/).

### G06 Wait for valid power before running fast

*Maker account.* Winterbloom traced dead modules to flash corruption during slow supply rise; the CPU started before full-speed operation was safe. **Reuse:** establish valid power before clock acceleration, then keep undervoltage reset active. Check slow ramps, rapid off/on cycles and dips. Thresholds depend on the actual MCU/flash. [Winterbloom brown-out account](https://blog.thea.codes/sam-d21-brown-out-detector/#brown-outs-slow-power-supply-rise-time-and-unfortunate-side-effects).

### G07 Verify recovery protection in the factory

*Maker account.* The same failure revealed valid-but-disabled bootloader protection; the bootloader did not enable it on their factory path. **Reuse:** read back protection configuration after programming, and exercise recovery on a fresh unit. Check an interrupted application update leaves the supported recovery path usable. [Winterbloom, A debugging story](https://blog.thea.codes/sam-d21-brown-out-detector/#a-debugging-story).

### G08 Use electrical polarity protection as well as connector cues

*Maker account.* Big Honking Button includes protection diodes despite keyed power connectors. **Reuse:** keying, labels and circuit protection serve different failure paths; select protection for the real current and voltage-drop budget. Check reverse connection on a current-limited fixture and verify normal-rail headroom. [Big Honking Button, Power](https://blog.thea.codes/designing-big-honking-button/#power).

## Electrical boundaries

### H01 Distinguish working range from survival range

*Maker account.* Castor & Pollux accepts a nominal 0–6 V pitch signal but conditions the input for signals beyond that range. **Reuse:** specify useful modulation range and non-destructive input range separately, including powered-off behavior; a software clamp cannot protect a pin. Check every jack at the promised limits and during power sequencing. [Castor & Pollux, Control voltage inputs](https://blog.thea.codes/designing-castor-and-pollux/#control-voltage-inputs).

### H02 Expect temporary output shorts while patching

*Maker account.* Castor & Pollux explicitly uses output series resistance for insertion/removal shorts. **Reuse:** test grounded tips and output-to-output connections, then separately verify pitch accuracy under load; an audio output circuit is not automatically a precision-CV output. [Castor & Pollux, Outputs](https://blog.thea.codes/designing-castor-and-pollux/#outputs).

### H03 Measure pitch voltage at the loaded jack

*Maker account.* Doepfer documents detuning from output protection resistors on A-156/A-170. **Reuse:** budget output impedance and destination fan-out as part of tuning accuracy. Example calculation: 1 kΩ feeding 100 kΩ loses 0.9901%; at 1 V/oct that is about 11.9 cents per commanded volt. Check one and several realistic loads. Removing protection is not the proposed remedy. [Doepfer DIY, 4.2.13](https://doepfer.de/DIY/a100_diy.htm).

## How to use this catalog

Each entry is a design recipe and a proposed check, not a claim that this library implements or validates the entire behavior. [Coverage](coverage.md) separates portable primitives from application policy, parameter tuning, and electrical or hardware measurements. A product must choose its own units, update rates, thresholds, transition policy, and test fixtures.

## Sources and scope

The linked code examples pin the inspected revisions: Mutable Instruments `f4cfa7697095a28d292bff758beb51deb49b5a86`; 4ms DLD `dfc4295fc9ca71be6243217ab544c2ef71705e3b`; monome crow `b340579d94e57e2b43336611b2c4037cff74bb80`; Winterbloom Castor & Pollux `652b28c950ed04ca41f0d8aa98d9b1be2f310f76`. Manual links identify versions where available; behavior can differ across firmware versions. The page numbers distinguish printed and PDF numbering when needed. [Attribution](../ATTRIBUTION.md) explains provenance and licensing.

These examples span Mutable Instruments, 4ms, Befaco, Intellijel, Xaoc Devices, Instruō, ALM, Make Noise, Noise Engineering, Expert Sleepers, Ornament & Crime, monome, Winterbloom and Doepfer. Maker technical accounts and release notes complement manuals. This is a curated set, not a complete survey.
