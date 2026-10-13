# Coverage and validation

The [catalog](catalog.md) contains 66 patterns. This table describes the public library's scope, not the status of any instrument. **Primitive** means a portable operation relevant to the entry exists in a header; the entry's full musical behavior still needs integration. **Recipe** means the catalog documents a design choice without a library implementation. **Measure** means the useful claim depends on a circuit, firmware schedule, UI, storage backend, or hardware test. A row can have a primitive and still require measurement. None of these rows asserts hardware qualification.

| Family | Public header | Contract available |
| --- | --- | --- |
| Jack presence | [`presence.h`](../include/eurorack_patterns/presence.h) | Caller-supplied probe evidence, complete windows, mismatch/streak thresholds, explicit startup policy, invalid-observation reset. Probe generation and electrical interpretation belong to the host. |
| Events | [`events.h`](../include/eurorack_patterns/events.h) | Sampled Schmitt rising edges, bounded pending count, overflow indication, initial-high policy. Cross-interrupt synchronization and actual acquisition timing belong to the host. |
| Controls | [`controls.h`](../include/eurorack_patterns/controls.h) | Neutral-centered bipolar mapping, motion threshold with endpoints, hysteretic step selection, and crossing/near-target pickup. Coefficients and ranges are examples, not calibrated recommendations. |
| Gestures | [`gestures.h`](../include/eurorack_patterns/gestures.h) | A press owns one role; consumption suppresses its release action. Hidden-edit mechanics and UI indication belong to the host. |
| Button timing | [`timing.h`](../include/eurorack_patterns/timing.h) | Debounced button state with separate on/off durations in caller-supplied milliseconds. External clock capture remains a separate path. |
| Pending changes | [`transitions.h`](../include/eurorack_patterns/transitions.h) | Retains the latest requested destination until the caller consumes it at a safe boundary. It does not choose that boundary or render a fade. |

The code expresses mechanisms with caller-defined time and electrical units. A host must establish its scan rate, voltage scaling, thread/interrupt ownership, invalid-sample policy, event overflow response, startup behavior, and acceptance criteria. Numeric values cited in the catalog describe particular source products. They are not drop-in defaults for new hardware.

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
| E01 | Recipe + measure | Select CV/gate ordering delay and verify latency with real sources. |
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
| E12 | Recipe + measure | Generate pulses to receiving-module width limits across tempo. |
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
| G01 | Recipe | Define usable fallback and notice for malformed imports. |
| G02 | Recipe + measure | Report calibration fallback; verify playable and accurate modes separately. |
| G03 | Recipe | Separate user reset from factory calibration and disclose save pauses. |
| G04 | Recipe + measure | Version, migrate, and validate fields; test interrupted writes separately. |
| G05 | Recipe + measure | Stop producers and clear pending/high outputs during panic. |
| G06 | Measure | Configure and verify power/brown-out behavior on actual silicon. |
| G07 | Measure | Read back recovery protection and test factory/update path. |
| G08 | Measure | Design and test reverse-polarity electrical protection. |
| H01 | Measure | Specify useful and survival input ranges including powered-off behavior. |
| H02 | Measure | Test output shorts and precision under realistic loads. |
| H03 | Measure | Measure loaded-jack pitch voltage and fan-out error. |
