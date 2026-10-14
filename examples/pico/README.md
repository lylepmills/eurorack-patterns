# Optional Raspberry Pi Pico reference adapter

This example targets the **original Raspberry Pi Pico / RP2040** (`PICO_BOARD=pico`).
It shares the host-tested [control adapter](../shared_control.h): a pot takes over
a stored value after pickup; a button alternates stored targets between 0.25 and
0.75; the onboard LED is on while the knob owns the value. There is no audio path.
This adapter is compile/link checked, **not hardware validated**.

## Bench wiring

Use a 10 kΩ potentiometer between the board's 3V3(OUT) and GND, with its wiper on
GP26 / ADC0. Connect a normally open pushbutton between GP15 and GND; the example
enables its internal pull-up. The non-wireless Pico's onboard LED uses GP25.
Consult the official [Pico pinout and hardware documentation](https://www.raspberrypi.com/documentation/microcontrollers/pico-series.html)
and [ADC/GPIO API](https://www.raspberrypi.com/documentation/pico-sdk/hardware.html).
Keep inputs within the board's 0–3.3 V range. **Do not connect Eurorack CV or gates
directly to this board.** Voltage scaling and input protection are outside this demo.

## Build

Install an ARM GNU embedded toolchain and put its `bin` directory on `PATH`.
Keep the SDK outside this repository. CI pins Raspberry Pi Pico SDK **2.3.1** at
`079c6f39023649b154152db30f1d781e884879bc`; the SDK retains its own licenses and
is not included in this MIT library's source distribution.

```sh
git clone --branch 2.3.1 --depth 1 https://github.com/raspberrypi/pico-sdk.git ../pico-sdk
cmake -S examples/pico -B build-pico -DPICO_SDK_PATH="$PWD/../pico-sdk" -DPICO_BOARD=pico -DCMAKE_BUILD_TYPE=Release
cmake --build build-pico
arm-none-eabi-size build-pico/patterns_pico.elf
```

The default build produces an ELF and does not fetch USB, network or flashing
utilities. It does not flash anything. Use the official SDK debug-probe workflow
if you choose to run it on your own board. This example intentionally contains no
automated flashing or device discovery.

## Adapter decisions and checks still needed

- Fresh blocking ADC reads feed a single foreground owner. Readings outside 12-bit
  range are invalid, but an in-range reading does not prove correct wiring or ADC
  health. There is no DMA/freshness-sequence scheme in this simple adapter.
- A loop gap over 10 ms breaks pickup history and button qualification before the
  current fresh ADC sample is processed. `sleep_ms(1)` is only a nominal cadence.
- A qualified press selects a new stored value; the 10 ms press/release durations
  and control tolerances are demonstration choices, not measured defaults.
- Measure slow/fast pickup, endpoints, contact bounce, startup with the button
  held, ADC noise and long foreground stalls. The LED only shows pickup ownership;
  it does not display the parameter value or prove output timing.

Report results with the [measured-trace issue form](https://github.com/lylepmills/eurorack-patterns/issues/new?template=trace.yml)
and [provenance requirements](../../docs/validation.md#trace-provenance).
