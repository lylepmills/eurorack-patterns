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
