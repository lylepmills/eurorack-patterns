# Coverage and validation

The [catalog](catalog.md) contains 88 patterns. This table describes the public library's scope, not the status of any instrument. **Primitive** means a portable operation relevant to the entry exists in a header; the entry's full musical behavior still needs integration. **Recipe** means the catalog documents a design choice without a library implementation. **Measure** means the useful claim depends on a circuit, firmware schedule, UI, storage backend, or hardware test. A row can have a primitive and still require measurement. None of these rows asserts hardware qualification.

| Family | Public header | Contract available |
| --- | --- | --- |
| Jack presence | [`presence.h`](../include/eurorack_patterns/presence.h) | Caller-supplied probe evidence, complete windows, mismatch/streak thresholds, explicit startup policy, invalid-observation reset. Probe generation and electrical interpretation belong to the host. |
| Events | [`events.h`](../include/eurorack_patterns/events.h) | Sampled Schmitt rising edges, bounded pending count, overflow indication, initial-high policy. Cross-interrupt synchronization and actual acquisition timing belong to the host. |
| Controls | [`controls.h`](../include/eurorack_patterns/controls.h) | Neutral-centered bipolar mapping, motion threshold with endpoints, hysteretic step selection, and crossing/near-target pickup. Coefficients and ranges are examples, not calibrated recommendations. |
| Gestures | [`gestures.h`](../include/eurorack_patterns/gestures.h) | A press owns one role; consumption suppresses its release action. Hidden-edit mechanics and UI indication belong to the host. |
| Button timing | [`timing.h`](../include/eurorack_patterns/timing.h) | Debounced button state with separate on/off durations in caller-supplied milliseconds. External clock capture remains a separate path. |
| Mapped pickup | [`pickup.h`](../include/eurorack_patterns/pickup.h) | Explicit arm/rearm, finite effective bounds, unreachable status, invalid-gap crossing reset. Destination snapping, UI and mapping remain host policy. |
| Pulse interval | [`pulses.h`](../include/eurorack_patterns/pulses.h) | Logical expiry, restart/ignore policies and cancellation. No separate-edge or physical timing guarantee. |
| Trigger delay | [`trigger_delay.h`](../include/eurorack_patterns/trigger_delay.h) | Fixed-capacity due masks in caller ticks. Same-bit/same-deadline events coalesce; cadence and acquisition belong to host. |
| Pending changes | [`transitions.h`](../include/eurorack_patterns/transitions.h) | Retains the latest requested destination until the caller consumes it at a safe boundary. It does not choose that boundary or render a fade. |

The code expresses mechanisms with caller-defined time and electrical units. A host must establish its scan rate, voltage scaling, thread/interrupt ownership, invalid-sample policy, event overflow response, startup behavior, and acceptance criteria. Numeric values cited in the catalog describe particular source products. They are not drop-in defaults for new hardware.

The [Daisy fault/startup measurements](validation.md#active-fault-and-startup-measurements)
add bounded physical evidence for pickup rearming/history breaks, gesture
cancellation and startup-held suppression in the example adapter. The public
corpus contains 15 complete runs across both passes. These checks do not promote
jack detection, audio/IRQ timing, brownout behavior or other boards to measured status.

See [research scope and unresolved reports](research-pass-2.md) and [executed checks versus hardware evidence](validation.md). Upstream tests cited in the catalog were read, not executed.

## Integration examples

The [shared-knob walkthrough](quickstart.md) and optional [Pico adapter](../examples/pico/README.md) compose pickup and motion acceptance with explicit validity and ownership. Host checks cover the application policy; ARM compile/link checks cover the example's build boundary. The [Daisy control bench](validation.md#daisy-seed3-control-bench) adds fresh ADC acquisition, buffered traces, gesture/gap policies and host replay. These add no hardware-qualified catalog entries.

## Per-pattern map

“Primitive” names the relevant family only; it does not claim an exact copy of the cited behavior. “Recipe” and “Measure” point to the evidence and test in the catalog. Implementation work should start with the portable primitive rows, then prioritize application policies and measurements by the intended product.

| ID | Coverage | What remains outside the library |
| --- | --- | --- |
| A01 | Primitive: presence | Generate and validate probes; choose window/streak/startup policy and measure insertion latency. |
| A02 | Measure | Verify ground/reference behavior with a single cable across power domains. |
| A03 | Recipe + measure | Design physical normalization and test silent/partially inserted cables. |
| A04 | Primitive: events | Scale thresholds to the circuit and test slow/noisy edges. |
| A05 | Primitive: events | Sample fast enough, synchronize producer/consumer, choose overflow policy. |
| A06 | Primitive: timing + measure | Button debounce exists; keep external clock capture on its own fast path and verify maximum rate. |
| A07 | Recipe | Test logical-to-physical mapping across every acquisition path and board variant. |
| A08 | Recipe; branch evidence | Aggregate internal/panel/MIDI ownership; cited fix is unmerged at snapshot. |
| B01 | Recipe + measure | Design per-role filters and measure response at the actual update rate. |
| B02 | Measure | Choose ADC topology and measure small CV after software attenuation. |
| B03 | Primitive: controls | Endpoints bypass motion rejection; other filters and endpoint remaps remain host work. |
| B04 | Measure | Characterize ADC settling at worst source impedance and mux jumps. |
| B05 | Measure | Calibrate gain/offset separately from noise reduction; verify intermediate points. |
| B06 | Recipe + measure | Provide raw per-path diagnostics in the host/factory protocol. |
| C01 | Primitive: controls | Neutral plateau mapping exists; choose physical tolerance and transfer law. |
| C02 | Recipe + measure | Define musical landing zones and test monotonicity/fine adjustment. |
| C03 | Primitive: controls | Stateful step hysteresis exists; choose scale and thresholds for the control. |
| C04 | Recipe | Implement hidden-edit entry threshold and stored secondary value in the UI. |
| C05 | Recipe | Relative catch-up is described; controls.h offers crossing pickup, a distinct policy. |
| C06 | Primitive: controls | Pickup exists; LEDs, CV target semantics, and mode transitions are host policy. |
| C07 | Primitive: controls (partial) | Motion rejection exists; the source's active tracking window is not implemented. |
| C08 | Primitive: gestures | Role consumption exists; timing and modifier precedence remain host policy. |
| C09 | Recipe | Expose and validate configurable hold timing in the product UI. |
| C10 | Primitive: gestures (partial) | Consume navigation modifier; channel selection and transport behavior remain host work. |
| C11 | Recipe | Decide which guard states persist with presets. |
| C12 | Recipe | Build every quantizer region from allowed membership; test negative/positive octaves and empty mask. |
| C13 | Primitive: pickup | Supply true effective bounds; handle snapped destinations, feedback and recovery explicitly. |
| C14 | Primitive: pickup (partial) | Caller must identify target/owner changes and explicitly re-arm. |
| D01 | Recipe | Render panel-selected and CV-effective state separately. |
| D02 | Recipe | Render stored, physical, and overridden ownership distinctly. |
| D03 | Recipe + measure | Design redundant cues and test readability in actual lighting. |
| D04 | Recipe | Define undo/redo scope and invalidation for product state. |
| D05 | Recipe | Define explicit return-to-panel semantics and audible transition. |
| D06 | Primitive: transitions (partial) | Latest pending value exists; UI indication, transport cancellation policy and musical commit boundary remain host policy. |
| D07 | Recipe | Distinguish armed cancellation from destructive erase in the application. |
| D08 | Recipe | Define reset domains so modes and recorded content stay separate. |
| D09 | Recipe | Build non-mutating contextual control help in the UI. |
| D10 | Recipe | Confirm costly operations and handle loading in application code. |
| D11 | Recipe | Invalidate views on edits and publish reload/bank resets without relying on musical clocks. |
| D12 | Recipe | Keep edit/play targets separate, render mismatch and define unlock/mode-exit behavior. |
| D13 | Recipe | Preserve stable focus identity across rebuild; choose fallback when the target disappears. |
| E01 | Primitive: trigger delay + measure | Delay mechanism exists; choose CV/gate skew budget and verify actual acquisition on hardware. |
| E02 | Recipe | Latch mode CV at note events; define behavior with trigger disconnected. |
| E03 | Recipe + measure | Set source-specific refractory time; test flams and fast attacks. |
| E04 | Recipe | Define reset/clock precedence at one processing boundary. |
| E05 | Recipe | Maintain pending/active rhythmic state and commit at a chosen boundary. |
| E06 | Recipe + measure | Separate transport, period acquisition, and phase; test first pulse. |
| E07 | Recipe + measure | Choose clock filtering and measure jitter/tempo response. |
| E08 | Recipe | Choose clock-loss/takeover policy for the instrument. |
| E09 | Recipe | Detect long-gap restart; choose timeout for sparse patterns. |
| E10 | Recipe | Require sustained evidence for a change in clock interpretation. |
| E11 | Recipe | Score competing predictors and choose confidence dynamics. |
| E12 | Primitive: pulses (partial) + measure | Logical width/expiry exists; tempo-dependent shortening and minimum physical high/low times remain host work. |
| E13 | Primitive: pulses | Choose retrigger policy, physical output service, polarity and any required inactive dwell. |
| E14 | Primitive: trigger delay | Supply reliable tick cadence; decide same-deadline multiplicity and reset/cancel policy. |
| F01 | Recipe + measure | Gate derived audio behavior during codec/rate reacquisition. |
| F02 | Primitive: transitions (partial) | Latest pending destination exists; fade serialization and audio processing remain host work. |
| F03 | Recipe | Preserve recording tail and blend at freeze boundaries. |
| F04 | Recipe | Classify reconfiguration and guard invalid audio state. |
| F05 | Recipe | Keep captured material independent of playback transforms. |
| F06 | Recipe | Choose slew/crossfade policy according to musical control mode. |
| F07 | Recipe + measure | Capture/dispatch queue and deadline/drop behavior need a host implementation; events.h only counts rising edges. |
| F08 | Measure | Rank and verify interrupt/audio deadlines on the target. |
| F09 | Recipe + measure | Serialize coherent saves and verify audio timing and power loss. |
| F10 | Recipe | Keep executing action's backing state alive during scene changes. |
| F11 | Recipe | Execute required side effects independently of disabled diagnostics; test deployed build variants. |
| F12 | Recipe | Capture deferred command context and define scene/global lookup semantics. |
| F13 | Recipe | Reserve in-flight work or dispatch copies; specify nested enqueue and full-queue policy. |
| F14 | Recipe + measure | Address every destination and use protocol-specific mute without unintended pitch edits. |
| F15 | Recipe + measure | Implement safe ownership/barriers for workers and dependent GUI/plugin objects. |
| F16 | Primitive: transitions (partial) | Peek/try-enqueue/Take composition is tested in event_paths.cpp; queue ownership and physical delivery remain host work. |
| F17 | Recipe | Choose per-message disconnect backlog policy and clear shared transport slots on early returns. |
| F18 | Recipe; branch evidence | Invalidate every derived route; cited fix is unmerged at snapshot. |
| F19 | Recipe | Revalidate adjacent protocols during replacement, preserving unrelated compatible edges. |
| G01 | Recipe | Define usable fallback and notice for malformed imports. |
| G02 | Recipe + measure | Report calibration fallback; verify playable and accurate modes separately. |
| G03 | Recipe | Separate user reset from factory calibration and disclose save pauses. |
| G04 | Recipe + measure | Version, migrate, and validate fields; test interrupted writes separately. |
| G05 | Primitive: pulses + trigger delay (partial) | Cancel/Reset clear logical work; host must stop producers, clear other queues and write physical idle outputs. |
| G06 | Measure | Configure and verify power/brown-out behavior on actual silicon. |
| G07 | Measure | Read back recovery protection and test factory/update path. |
| G08 | Measure | Design and test reverse-polarity electrical protection. |
| G09 | Recipe | Test real packed schemas, guard bytes and migration of changed wire layouts. |
| G10 | Recipe + measure | Specify page validity, initial/wrapped generation ordering, gap scan and power-cut recovery. |
| G11 | Recipe | Test all persisted semantic names against runtime mappings across schema versions. |
| H01 | Measure | Specify useful and survival input ranges including powered-off behavior. |
| H02 | Measure | Test output shorts and precision under realistic loads. |
| H03 | Measure | Measure loaded-jack pitch voltage and fan-out error. |
