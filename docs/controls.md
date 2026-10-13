<!-- SPDX-License-Identifier: MIT -->
<!-- Copyright 2026 Lyle Mills -->
# Physical controls and button gestures

`controls.h`'s convenience wrappers use physical travel in percent,
**0..100**. The caller converts ADC readings to this range before calling
them. `BipolarAmount` maps that range to an effective **-100..100** amount;
its default neutral halfwidth is 2 percentage points, so physical 48..52 is
one neutral value. A valid custom halfwidth is finite and in [0, 50).
`ArmPickup` and `UpdatePickup` compare bipolar knobs in that effective domain.
Their default 0.5 tolerance is **strict** for catching: a difference exactly
0.5 arms pickup and does not count as near on an update. A crossing catches
even if the sample skips the target. Once caught, `base` follows accepted
physical samples. These functions work directly with existing parallel arrays
of `physical`, `base`, and `catching`. `UpdatePickup` reports a changed base
**or** a completed catch, even if the physical and base values coincide.

For another mapping, map the physical and stored values yourself and use
`PickupRequired(mappedPhysical, mappedTarget, tolerance)` to decide whether to
arm. On accepted motion, use `PickupCrossed(mappedPrevious, mappedCurrent,
mappedTarget, tolerance)` to decide whether to catch. All three values must be
finite and in the same domain, such as volts, hertz, or log-frequency units.
Both pure helpers return false on invalid inputs; the caller retains its state.
The tolerance is measured in that mapped domain.

Seed each control's physical/accepted position from the first valid reading.
At startup with no stored target, also set its base to that position and leave
catching false. On a mode change or after a shifted movement, call `ArmPickup`
for each affected control. A shift with no movement leaves an existing catch
alone. For each later reading, call `AcceptMotion(candidate, physical[i])`;
only when it returns true call `UpdatePickup(previous, physical[i], base[i],
bipolar, catching[i])`. `AcceptMotion` tests against the last accepted sample,
so a succession of small changes eventually crosses its 0.6% threshold. Exact
endpoints are accepted immediately. The caller owns repaint/fade timing.

The percent wrappers reject invalid positions, nonfinite values, and invalid
thresholds without changing caller state. `BipolarAmount` returns NaN for
invalid input. The default tolerances are configurable convenience values; a
different tolerance must be finite and positive. `SelectHysteretic` takes a
normalized 0..1 input, positive step count, previous index (or -1 at startup),
and hysteresis in step units. A negative hysteresis disables hysteresis;
otherwise it must be less than 0.5. Invalid input returns the previous index.
Keep one previous index per independent selector.

`gestures.h`'s `RoleLatch<Role>` is owned by one button's event handler.
Choose a typed role from the current UI state on `Press`. Duplicate presses
are ignored. On release, act only when `Release(role)` returns true; it gives
the **press-time** role even if navigation changed the page. A combined
gesture calls `Consume()` and performs its end action immediately; the later
release is swallowed. `Cancel()` has the same release suppression for aborted
gestures. A consumed latch remains pressed until physical release. Route all
events for a button through one latch; the API has no locking and must be
owned by one event thread or protected by the caller.

For a button that doubles as a modifier and navigation control, choose its
role on press. A navigation role can execute immediately and consume the
gesture. A combination can end its modifier role immediately and consume the
remaining release before navigating. The later physical release only clears
the latch. These headers contain no hardware drivers; tests exercise portable
traces and boundaries, not a hardware validation claim.
