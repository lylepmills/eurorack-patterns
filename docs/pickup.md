# Pickup across restricted mapped ranges

New integration? Start with the [complete shared-knob walkthrough](quickstart.md).

`PickupLatch` answers whether a mapped physical sample may be applied to a stored parameter. It is useful when a control bank, preset, or other owner has moved the destination while a physical knob stayed put. The caller supplies mapped values in one consistent unit: the two reachable endpoints, the stored target, and each observed sample. This helper does not perform the mapping, sample filtering, or parameter write.

The caller must ensure the two endpoints bound every valid mapped sample. A curve that overshoots both endpoints needs its true reachable bounds instead. The latch has no time base, allocates no memory, starts unconfigured and unarmed, and is mutable single-owner state; serialize calls if an interrupt or another thread can touch the same instance.

```cpp
#include <eurorack_patterns/pickup.h>

eurorack_patterns::PickupLatch pickup;
pickup.Configure(0.2f, 0.8f, 0.01f);  // mapped endpoints, tolerance
pickup.Arm(stored_value);
if (pickup.state() == eurorack_patterns::PickupLatch::State::kUnreachable) {
  // Tell the player the current mapping cannot reach the stored value.
}
if (pickup.Observe(mapped_knob_sample, sample_valid)) {
  set_parameter(mapped_knob_sample);
}
```

`Configure(a, b, tolerance)` accepts finite endpoints in either order, including equal endpoints, and a finite positive tolerance. On success it disarms the latch; on failure it leaves the previous configuration and state intact. `Arm(target)` accepts a finite target only after configuration, clears observation history, and enters `kWaiting` or `kUnreachable` according to the inclusive endpoint interval. An invalid arm leaves state intact. `Disarm()` clears the state and history while retaining the configuration.

`Observe(sample, valid)` returns **permission to apply**, including on every valid sample after pickup. It is not a changed-value event. The sample must be finite and within the configured endpoint interval. While waiting, the first valid sample may catch when its distance from target is strictly less than tolerance. A later pair of consecutive valid samples may also catch by straddling the target, even if a coarse scan skips it. An invalid, nonfinite, or out-of-range observation returns false and breaks that pair, but preserves the target and state. An unreachable arm never applies a sample or jumps the target to an endpoint.

The caller must explicitly call `Arm` again when another owner changes the stored value or when the mapping changes. Endpoint bounds are a necessary continuous-range check, not a proof that every interior value is attainable. For a stepped or quantized destination, choose an effective domain and application policy from its actual reachable values; after applying, read back the value the destination kept. This helper makes no discrete pickup guarantee and has no automatic jump mode. A zero-width range can pick up only its single endpoint; arming another target reports unreachable.

The motivating failure cases were observed in 4ms MetaModule's [mapped-range catch-up change](https://github.com/4ms/metamodule/commit/1f053d1fd16b654940ef865ee5305a6a8cc79d1f) and [destination-change re-arm change](https://github.com/4ms/metamodule/commit/0d1d5d92834d9af87a2bda77f116b24ea33278da). MetaModule checks at an end stop and offers a separate jump policy; this independent MIT helper reports an out-of-range target at arm time and leaves application policy to the caller. It contains no upstream implementation text or mapping algorithm. Host tests use synthetic samples; they do not validate hardware control noise, scan timing, or a particular destination's quantization.

## One stepped-destination policy

[`stepped_control.h`](../examples/stepped_control.h) is an original application
example for the finite set `{0, 0.25, 0.5, 0.75, 1}`. It composes the existing
`PickupLatch`; it is not an installed API or a policy for arbitrary quantizers.
The [runnable example](../examples/stepped_pickup.cpp) demonstrates takeover,
readback, an incompatible saved value and explicit recovery.

The physical input is already mapped into `[0,1]`. The destination snaps to the
nearest member, with exact midpoint ties going upward. Pickup matches **after
snapping**, using integer step indices `0..4` and tolerance `0.5`: only identical
steps match directly. For example, a sample of `0.44` selects the stored `0.5`
step and can pick up immediately, before reaching the raw `0.5` position.

| Situation | Example policy |
| --- | --- |
| First valid sample selects the target step | Take ownership immediately. |
| Consecutive valid samples skip over the target step | Take ownership and apply the current sample's step. A coarse `0 → 1` sweep across a `0.5` target therefore writes `1`, not `0.5`. |
| Invalid, nonfinite or out-of-range sample | Do not write. Break crossing history; a later sample cannot prove a crossing through the gap. Existing tracking ownership survives a gap. |
| External edit, preset or bank change | Call `Rearm()` after the destination changes, even for an equal value. Read the actual stored target and discard all previous sample history. |
| Stored target is not a member, such as `0.4` | Report `kUnreachable`, retain the stored value, and block knob writes. Recovery requires an explicit user/preset edit to a supported member followed by `Rearm()`. |
| Write produces an unexpected readback | Return `kMismatch` and re-arm from that actual value. A supported value waits for pickup again; an unsupported/nonfinite value becomes unreachable. |

The destination supplies synchronous `ReadNormalized()` and
`WriteNormalized(float)` methods. The adapter sends the original normalized
sample to the destination, then reads back what was actually stored. `Sample`
returns `kNone` when no write occurs, `kMatched` when readback equals the expected
snapped member, or `kMismatch` when readback differs from that member. A rejection
or extra adjustment can cause a mismatch. These are
write outcomes, **not changed-value events**: repeated tracking samples can
produce repeated matched writes without changing the value.

Use `value()` for stored-value feedback, never the raw request. Show waiting,
tracking or unreachable status separately; for an unsupported saved value, show
that value and an explicit recovery action rather than a misleading pickup arrow.
Nonfinite readback needs an invalid-value indication. Calling `Rearm()` alone
cannot repair an unsupported target, and the adapter never silently snaps saved
state. Membership is exact here because quarters are exactly representable;
other scales should define canonical step IDs rather than borrow this equality
test or widen it with an unexplained epsilon.

Keep the destination and adapter in one serialized ownership context, and keep
the destination alive for the adapter's lifetime. Report every external edit;
the adapter does not poll for unreported changes. Its five-member mapping is
fixed. Deferred/asynchronous writes, changing scales, hysteretic/nonmonotone
quantizers and noisy boundary behavior need separate policies. No motion filter
or hysteresis is added here; physical control feel remains unmeasured.

Run the example and synthetic checks from a repository checkout:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
ctest --test-dir build -C Release -R "example_stepped_pickup|test_stepped_control" --output-on-failure
```

The [independent finite-set oracle](../tests/test_stepped_control.cpp) enumerates
nearest members and traversed steps without using `PickupLatch` or the adapter's
snapping code. It checks all 7,776 four-sample sequences over five step values
plus an invalid sample, across five reachable targets and one unreachable target.
Additional checks cover slow sweeps in both directions, values immediately
around exact midpoints, external edits (including equal values), invalid gaps,
rejected/coerced writes and explicit recovery. These establish the example's
declared software policy, not hardware feel or general quantizer correctness.
