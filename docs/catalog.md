# Eurorack micro-pattern catalog

Research snapshot: 13 October 2026. A catalog of 88 small design choices that can make a module feel predictable while patching, playing, editing and recovering from mistakes. The emphasis is on reusable behavior rather than synthesis algorithms.

The strongest common principle is to separate **what the user or signal is doing** from **when it is safe and musically appropriate to act on it**. Jack presence, gate edges, knob movement, clock acquisition and preset loading need different policies. A blanket “debounce everything” or “smooth everything” rule breaks useful behavior.

Each entry identifies **Code**, **Manual**, **Maker account**, or **Release notes** evidence. The second pass also identifies fixes, upstream tests, and unmerged branch evidence explicitly. Observed behavior belongs to the cited product/version; reuse ideas and checks are proposed applications. The checks are a test backlog, not results from a hardware evaluation. Numeric constants are examples tied to their original scan rates and circuitry. The initial survey is now extended by a [source and bug-history pass](research-pass-2.md). This remains a curated investigation, not an exhaustive module or firmware audit.

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

- [Jack presence and trigger capture](#jack-presence-and-trigger-capture) — A01–A08
- [Analogue acquisition and filtering](#analogue-acquisition-and-filtering) — B01–B06
- [Knobs and gestures](#knobs-and-gestures) — C01–C14
- [Visible state and reversible actions](#visible-state-and-reversible-actions) — D01–D13
- [Musical timing and synchronization](#musical-timing-and-synchronization) — E01–E14
- [Audio transitions and runtime isolation](#audio-transitions-and-runtime-isolation) — F01–F19
- [Startup storage and recovery](#startup-storage-and-recovery) — G01–G11
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

### A07 Keep logical jack identity separate from physical pins

*Code and fix.* O_C immediate reads accidentally used logical input numbers as GPIO numbers; this worked on the normal layout and failed on the flipped panel. The fix applies the board mapping to both read paths. **Reuse:** make logical IDs and hardware addresses separate domains. **Counterexample/check:** permute every pin in a fake board adapter; interrupt, sampled, immediate and diagnostic reads must still agree on jack identity. A mapping used by only one path is insufficient. [Fix](https://github.com/mxmxmx/O_C/commit/85dcb4c385b38a37b2643db76d05bec09bd8e589).

### A08 Keep aggregate presence until the last source leaves

*Code and tests, unmerged branch at this snapshot.* MetaModule's proposed fix derives destination presence from internal cables plus live panel/MIDI routes. **Reuse:** removing one source must not disconnect a summed destination still owned by another. **Counterexample/check:** A+B feed X; remove A, then B; X becomes unpatched only after B. Repeat with an internal cable remaining. This concerns logical routing, not electrical jack detection. The cited change was absent from main/v2.4.0 on the research date. [Predicate and tests](https://github.com/4ms/metamodule/commit/c4da22c9fe1df78c22b9f295bef10dc03cfd6af4).

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

### C12 Apply quantizer membership in every octave and direction

*Code and fix.* O_C corrected masked-scale codebook generation because its descending region still included disabled notes; the fix added a host test spanning positive and negative octaves. **Reuse:** derive every region from the same allowed-note set before adding hysteresis. **Counterexample/check:** enable only two pitch classes and sweep below/above zero in both directions; every result must belong to that set. Define the empty-mask policy separately. Hysteresis cannot repair an invalid codebook. [Fix and regression](https://github.com/mxmxmx/O_C/commit/fdf829d050f2094ec4d3c77d6f696d2e419f0f9a).

### C13 Tell the user when pickup cannot reach its target

*Code and tests.* MetaModule checks out-of-range catch-up at physical endpoints, accounts for inverted mappings, and offers an endpoint-jump policy. **Reuse:** report impossible pickup explicitly. **Counterexample/check:** stored .9 with continuous reachable range [.2,.8] can never cross; reversed endpoints do not change that. Snapped destinations require effective-value reachability and write/readback, not just raw endpoint bounds. Our [PickupLatch](pickup.md) reports outside-range targets at arm time and never jumps automatically; that is an independent, narrower contract. [Change and inverted snapped test](https://github.com/4ms/metamodule/commit/1f053d1fd16b654940ef865ee5305a6a8cc79d1f).

### C14 Re-arm when another owner changes the pickup target

*Code and fix.* MetaModule added destination-value comparison when resetting catch-up, alongside physical-position comparison. **Reuse:** unchanged physical position does not prove continued control ownership. **Counterexample/check:** knob .2 controls A=.2; another bank changes A to .7; returning to the first bank must re-arm before its next small move. Explicitly notify pickup of target/binding changes. For snapping destinations, compare the accepted effective value, not merely the last requested value. [Reset change](https://github.com/4ms/metamodule/commit/0d1d5d92834d9af87a2bda77f116b24ea33278da).

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

### D11 Refresh the edit target even when the clock is stopped

*Code and fix.* Ansible preset selection changed its action target while leaving the grid stale when an external clock cable was connected but silent. The fix invalidates the display on selection itself. **Reuse:** direct edits must publish visible state independently of musical callbacks. **Counterexample/check:** stop clock, select B, then save: both displayed and actual target must be B. MetaModule similarly publishes a control-bank reset during patch load to synchronize its page manager. [Ansible fix](https://github.com/monome/ansible/pull/109), [MetaModule reset publication](https://github.com/4ms/metamodule/commit/d3cfb160dc5275a562fee9dee94ab56928cb47b1).

### D12 Separate the pattern being edited from the pattern playing

*Code and feature change.* Ansible Kria can latch an edit target while its meta sequence continues playing other patterns, and indicates the mismatch. **Reuse:** assign play, edit and display targets deliberately. **Counterexample/check:** lock editing to A, play A/B/C, edit a step; only A changes and playback continues. Test unlock and mode exit. This is a latched lock entered with a modifier gesture, not necessarily a hold-to-lock interaction. [Behavior and gesture](https://github.com/monome/ansible/pull/82).

### D13 Restore focus by stable identity after rebuilding a list

*Code and fix.* MetaModule changed knob-set focus restoration from vector position to panel-control identity. **Reuse:** retain the object the user chose when sorting, inserting or removing nearby entries. **Counterexample/check:** focus control 5; insert a mapping before it; the next edit must still affect control 5. If the focused object itself disappears, choose and display an explicit fallback. A surviving numeric list index is not proof the same object survived. [Identity change](https://github.com/4ms/metamodule/commit/1fe729fa7da2e81635ea55ff439737d3fb5be9e3).

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

*Second-pass code evidence.* Ansible seeds the first interval after reset from its last valid period, avoiding a long stopped interval becoming the first gate/ratchet duration. **Counterexample:** stop for five seconds, reset, then restart at a new tempo; using the old period gives predictable startup but one cycle of tempo lag. Fresh boot without a valid period needs a separate policy. [Implementation and tradeoff](https://github.com/monome/ansible/pull/71).

### E07 Choose clock smoothing for the musical job

*Code and manual.* **Observed:** DLD offers clock-period deadbands and averaging options with different tempo-response times. **Reuse:** stabilize a delay without discarding intentional tempo modulation. **Check:** random jitter, swing, drift and abrupt tempo changes; measure settling and missed/double events. Source contains experimental modes beyond the released choices. [DLD v5 notes](https://4mscompany.com/DLD/manual/V5-Release-Notes.pdf), [clock filters](https://github.com/4ms/DLD/blob/dfc4295fc9ca71be6243217ab544c2ef71705e3b/buttons_jacks.c#L175-L287).

### E08 Hold the last tempo until deliberate takeover

*Manual.* **Make Noise Mimeophon.** **Observed:** after clock disappears, established timing continues until Rate changes. **Reuse:** avoid surprising jumps during clock interruptions; support tap tempo. **Caveat:** this policy suits effects better than every transport. **Test:** missing pulses, stopped clock, cable removal, then knob movement. (p.13) [Mimeophon manual](https://www.makenoisemusic.com/wp-content/uploads/2024/03/mimeophon-manual.pdf). A different deliberate policy is QCD auto-stop: effects and trigger generators need not agree. [QCD v2, p.2](https://4mscompany.com/QCD/QCD-manual-v2.pdf#page=2).

*Unresolved counterexample.* O_C issue #75 reports multiplied output continuing after its external parent clock stops; the maintainer attributes this to the internal timer. The report remained open at this snapshot. Use it to test subordinate clock stop/restart policy, not as proof of a current fix or a universal need to stop. [Report and discussion](https://github.com/mxmxmx/O_C/issues/75).

### E09 Treat a clock restart as a distinct event

*Code.* **Observed:** Marbles recognizes a sufficiently long gap, resets train phase/counters, and raises a downstream reset instead of treating the gap as an ordinary period. **Reuse:** distinguish transport stop/restart from tempo change. **Tradeoff/test:** intentionally sparse clocks need a suitable timeout; test missing pulses and long rests. [Restart handling](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/marbles/ramp/ramp_extractor.cc#L185-L203).

### E10 Require sustained evidence before switching input interpretation

*Code.* **Observed:** Marbles switches to audio-rate clock processing only after consecutive qualifying pulses; the period threshold also has hysteresis. **Reuse:** protect automatic regime/mode detection from brief excursions. **Tradeoff/test:** delayed mode entry; test chirps and signals hovering at the boundary. [Regime detection](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/marbles/ramp/ramp_extractor.cc#L205-L217).

### E11 Earn estimator trust slowly; withdraw it quickly

*Code.* **Observed:** Marbles scores competing clock predictors with asymmetric smoothing: confidence rises slowly and falls quickly after error. **Reuse:** confidence-based automatic choices should abandon a broken assumption promptly. **Tradeoff/test:** possible estimator churn; test steady jitter, alternating intervals, and sudden tempo changes. [Predictor scoring](https://github.com/pichenettes/eurorack/blob/f4cfa7697095a28d292bff758beb51deb49b5a86/marbles/ramp/ramp_extractor.cc#L108-L167).

### E12 Keep trigger pulses separate at high rates

*Code.* **Observed:** In trigger mode, DLD limits clock-output high time to the lesser of half-period and its trigger-duration limit; gate mode uses half-period. **Reuse:** shorten nominally fixed pulses before they merge into a sustained gate. **Check:** sweep tempo and multiplication across the crossover, measuring both minimum high and low times against receiving modules. [DLD timer](https://github.com/4ms/DLD/blob/dfc4295fc9ca71be6243217ab544c2ef71705e3b/timekeeper.c#L49-L69).

*Second-pass fix evidence.* Teletype replaced a 10 ms pulse countdown with per-output timers after pulse-width errors up to 9 ms; the PR author reports scope verification. This pass did not repeat that measurement. A logical 3 ms pulse serviced at 0 and 10 ms still lasts 10 ms physically. Test output service under load as well as the [retrigger policy](#e13-specify-whether-retriggers-extend-a-level-or-create-new-edges). [Timing fix](https://github.com/monome/teletype/pull/310).

### E13 Specify whether retriggers extend a level or create new edges

*Code.* Teletype restarts an output's off timer when pulsed again; an already-active output stays active. **Reuse:** name the retrigger policy instead of calling every request a delivered trigger. **Counterexample/check:** width 10, requests at 0 and 5: restart ends at 15; ignore-while-active ends at 10; neither creates an edge at 5. Our [PulseTimer](pulses.md) supports those two policies. Separate edges require a queue, minimum inactive dwell and sufficiently prompt output service. [Pulse operation](https://github.com/monome/teletype/blob/e390bacdf024f2234e2ade6a4821773b9a80a322/src/ops/hardware.c#L477-L489), [timer replacement](https://github.com/monome/teletype/blob/e390bacdf024f2234e2ade6a4821773b9a80a322/module/main.c#L1051-L1056).

### E14 Preserve trigger identity throughout an acquisition delay

*Code and fix.* O_C replaced a shared pending trigger mask with independent input histories. A later input could otherwise overwrite the identity attached to an earlier deadline. **Reuse:** preserve payload/identity as well as event time. **Counterexample/check:** A at tick 0, B at tick 1, delay 3 must yield A at 3 and B at 4. Our [TriggerDelay](trigger-delay.md) stores due masks by tick. Same-channel events with the same deadline coalesce; choose counters/queues if multiplicity matters. [Replacement](https://github.com/mxmxmx/O_C/commit/cc2b6985c71a5aab5de8eba7a992b191b261a511).

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

*Code, fix and release notes.* Ansible pauses I²C follower reception around large flash writes after save-time lockups and reported preset loss under external commands. It restores the listening address for the current app afterward. **Reuse:** serialize a coherent snapshot and explicitly exclude or queue concurrent writers. **Counterexample/check:** send external edits throughout save, reload the result and verify command reception resumes correctly. The transport-specific pause is not a generic storage transaction. Separately, disting EX v1.12 removed save-related audio interruptions. Neither fix establishes atomic power-loss recovery. [Ansible report](https://github.com/monome/ansible/issues/86), [save fix](https://github.com/monome/ansible/pull/87), [disting release note](https://www.expert-sleepers.co.uk/distingEXfirmwareupdates.html).

### F10 Keep the executing action stable during a scene switch

*Code and fix.* Teletype copies the command being interpreted before a `SCENE` operation can replace its backing scene data. **Reuse:** retain the current unit of work across a destructive state replacement; separately specify which later operations see new global state. **Counterexample/check:** a command changes scene in its first subcommand and then reads later tokens; those tokens must belong to the original command. This protects command storage, not an entire scene transaction. Deferred context needs its own policy ([F12](#f12-capture-delayed-execution-context-deliberately)). [Fix and reproducer](https://github.com/monome/teletype/pull/278), [current copy](https://github.com/monome/teletype/blob/e390bacdf024f2234e2ade6a4821773b9a80a322/src/teletype.c#L229-L292).

### F11 Keep required side effects outside diagnostic macros

*Code and fix.* O_C added explicit save/restore calls for builds where the logging macro removes its arguments. **Reuse:** logging and assertions must observe required work, not be the only reason it executes. **Counterexample/check:** compile with diagnostics on and off; save, cold-load and compare values and call counts. Release-only data loss can escape debug tests. This does not establish flash atomicity or real-time safety. The library's own test checks remain active with `NDEBUG`. [Fix](https://github.com/mxmxmx/O_C/commit/a8e8cc9b2beddfac6dc0ca0ee1f808c02f55a033).

### F12 Capture delayed execution context deliberately

*Code and fix.* Teletype fixed a delayed command losing its loop/script context by storing that context with the command. **Reuse:** specify snapshot versus live lookup for each deferred field. **Counterexample/check:** enqueue an action for output I=1, change I before it runs, and verify the documented target. Nested execution and scene changes also need explicit lifetime rules. Copying command bytes alone cannot preserve implicit context. [Report](https://github.com/monome/teletype/issues/130), [Fix](https://github.com/monome/teletype/commit/366bd7c1b169d4bc7d2bda02c83d30a76c07a08e).

### F13 A due callback's slot is not yet free

*Code and fix.* Teletype reserved a due delay slot while executing its callback, preventing nested enqueue from reusing a slot that the outer operation would subsequently clear. **Reuse:** distinguish queued, executing and free ownership. **Counterexample/check:** A becomes due in slot 0; A enqueues B; A finishes; B must survive exactly once. Also fill the queue and define whether child work can run in the same service pass. Copy-out dispatch is another possible design; the upstream reservation is not a universal scheduler. [Report](https://github.com/monome/teletype/issues/80), [Fix](https://github.com/monome/teletype/commit/adfd2aa0ea962639a6e48e1e7c6b777df364363b).

### F14 Silence a voice without unnecessarily rewriting its pitch

*Code and fix.* Ansible changed W/syn muting from a combined pitch/velocity command to velocity-only; the same fix corrected destination indexing with multiple followers. **Reuse:** use the narrowest reset operation that achieves silence, and address every intended destination. **Counterexample/check:** load a preset during a release tail at nonzero pitch; mute without a pitch-zero jump. Repeat with multiple followers. Some instruments deliberately reset pitch; define that separately from mute. [Fix and reported behavior](https://github.com/monome/ansible/pull/107).

### F15 Stop new users and finish current users before teardown

*Code and fix.* MetaModule paused task runners and waited for in-flight reads before patch unload after double-close/iterator-lifetime problems. A later fix disposes plugin-created GUI objects before unloading their plugin code. **Reuse:** prevent new work, drain current work, destroy dependents, then free their provider. **Counterexample/check:** hold a fake read at a barrier during reload; its file must remain alive until it exits and close exactly once. Blocking this barrier in an audio callback would introduce another failure. [Async fix](https://github.com/4ms/metamodule/commit/c48f3d1f2e24b991721a39760f12eb4f7ef414c5), [GUI/deleter fix](https://github.com/4ms/metamodule/commit/86f7d5cebf532b75e03d76fbb71655890bf23ee1).

### F16 Advance last-queued state only after enqueue succeeds

*Code and fix.* MetaModule feedback checks queue capacity before enqueuing and updating remembered values. **Reuse:** rejected work must remain retryable; distinguish requested, queued and delivered state. **Counterexample/check:** full queue rejects value 127; drain it; unchanged 127 must still enqueue on retry. Gate-off loss can leave a receiver sounding. A check-then-put sequence needs single-producer ownership or an atomic try-enqueue operation. Queued does not mean physically delivered. [Feedback fix](https://github.com/4ms/metamodule/commit/03677724065c4388a22c83f5fd057f524aa0806d).

### F17 Define what disconnected transports discard

*Code and fix.* MetaModule clears shared MIDI slots and drains generated output while disconnected, including the no-patch path, to avoid echo and stale bursts after attachment. **Reuse:** specify disconnect backlog policy and execute cleanup on early returns too. **Counterexample/check:** generate messages unplugged, reconnect, verify no old burst and that fresh messages pass. This policy is appropriate for stale performance events; durable transfers may need retry instead. [Transport fix](https://github.com/4ms/metamodule/commit/03d9e0fb7b73d4743496231ddc48b65a57b834f9).

### F18 Remove every derived route when deleting its source mapping

*Code and tests, unmerged branch at this snapshot.* MetaModule's proposed removal fix rebuilds panel/MIDI and summed routes from patch data. **Reuse:** invalidate every cached form of a deleted relationship. **Counterexample/check:** map pitch→X, remove it, map gate→X; pitch must stop controlling X while gate works. Preserve unrelated internal cables. A destination retaining its last value does not prove the old route is still live. This change was absent from main/v2.4.0 on the research date. [Removal and tests](https://github.com/4ms/metamodule/commit/c3f74800f8bf43b4ddc77967881cad12611b02b6).

### F19 Revalidate relationships when an object is replaced in place

*Code and tests.* MetaModule removes adjacent expander links when substituting a module, even when ordinary cables are retained. **Reuse:** a stable slot ID does not imply the new object supports the old protocol. **Counterexample/check:** replace B in A—B—C—D with an incompatible type; remove A—B and B—C, retain C—D. Validate each relationship by its semantics; blindly preserving or clearing the whole graph both lose useful behavior. [Replacement and test](https://github.com/4ms/metamodule/commit/70b0314b1207416ba9ae3f7f493899882e295dec).

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

*Code, manual and fixes.* Teletype KILL stops its metronome, clears delayed work and forces trigger outputs low; fixes addressed already-high outputs and active pulse timers. **Reuse:** cancel producers and pending/active work before forcing the intended idle level. **Counterexample/check:** panic during a pulse and before a delayed retrigger; advance beyond both old deadlines and verify no internal work reasserts the output. Our `PulseTimer::Cancel` covers one logical pulse; the host still owns queues, polarity, physical writes and external-input policy. [High-output fix](https://github.com/monome/teletype/commit/e88fd9d6a61f494a336a90f0fbf1d966471095b2), [active-pulse fix](https://github.com/monome/teletype/pull/310), [KILL sequence](https://github.com/monome/teletype/blob/e390bacdf024f2234e2ade6a4821773b9a80a322/src/ops/controlflow.c#L341-L352).

### G06 Wait for valid power before running fast

*Maker account.* Winterbloom traced dead modules to flash corruption during slow supply rise; the CPU started before full-speed operation was safe. **Reuse:** establish valid power before clock acceleration, then keep undervoltage reset active. Check slow ramps, rapid off/on cycles and dips. Thresholds depend on the actual MCU/flash. [Winterbloom brown-out account](https://blog.thea.codes/sam-d21-brown-out-detector/#brown-outs-slow-power-supply-rise-time-and-unfortunate-side-effects).

### G07 Verify recovery protection in the factory

*Maker account.* The same failure revealed valid-but-disabled bootloader protection; the bootloader did not enable it on their factory path. **Reuse:** read back protection configuration after programming, and exercise recovery on a fresh unit. Check an interrupted application update leaves the supported recovery path usable. [Winterbloom, A debugging story](https://blog.thea.codes/sam-d21-brown-out-detector/#a-debugging-story).

### G08 Use electrical polarity protection as well as connector cues

*Maker account.* Big Honking Button includes protection diodes despite keyed power connectors. **Reuse:** keying, labels and circuit protection serve different failure paths; select protection for the real current and voltage-drop budget. Check reverse connection on a current-limited fixture and verify normal-rail headroom. [Big Honking Button, Power](https://blog.thea.codes/designing-big-honking-button/#power).

### G09 Finalize partial packed settings and verify encoded sizes

*Code and fix.* O_C corrected a trailing packed-nibble save and bumped its app-data version. **Reuse:** verify size, field alignment and final partial bytes for every persistent schema. **Counterexample/check:** round-trip `[U4]`, `[U4,U4]`, `[U4,U8]`, `[U8,U4]` and real layouts with guard bytes beyond the declared size. Changing the wire layout also needs migration/version policy; a passing round-trip on the new format does not establish old-data compatibility. [Fix](https://github.com/mxmxmx/O_C/commit/ebf96f32a0cdc3e34362f30c49bd124786cdb96e).

### G10 Discover a journal's first valid generation before ordering it

*Code and fix.* O_C fixed page scanning that rejected a valid first page unless its generation was zero. **Reuse:** bootstrap from a valid record before comparing sequence order; physical page index and generation need not match. **Counterexample/check:** valid pages with generations 17 and 18 must recover 18. Also test corrupt-first-page, gaps, sequence wrap and partial erase. A fast scan that stops at a gap can miss recoverable later pages; neither a checksum nor this fix proves power-loss safety. [Fix](https://github.com/mxmxmx/O_C/commit/1495d028e4e3062bde3eefa5ef216aea008dfbfd).

### G11 Preserve semantic identifiers across enum changes

*Code and fix.* Ansible fixed an omitted serialized enum label that made MIDI load the wrong app after adding another mode. **Reuse:** test stable persisted meaning against runtime enum mappings. **Counterexample/check:** load every old named value after inserting a new runtime enum member; each must still select the same behavior. Unknown names need an explicit fallback/error. String serialization helps only when the string-to-enum table remains correct; bounds checks alone cannot detect a valid but wrong mode. [Fix and schema explanation](https://github.com/monome/ansible/pull/65).

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
