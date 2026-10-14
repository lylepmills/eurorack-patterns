// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "../shared_control.h"
#include <eurorack_patterns/timing.h>
#include "pico/stdlib.h"
#include "hardware/adc.h"

// Raspberry Pi Pico (RP2040), single foreground owner. No audio or Eurorack I/O.
// GP26/ADC0: 0..3.3 V pot wiper. GP15: normally open button to ground.
int main() {
  adc_init();
  adc_gpio_init(26);
  adc_select_input(0);
  gpio_init(15);
  gpio_set_dir(15, GPIO_IN);
  gpio_pull_up(15);
  gpio_init(PICO_DEFAULT_LED_PIN);
  gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);
  example::SharedControl control;
  eurorack_patterns::DebouncedButton button;
  if (!control.Reset(0.25f) || !button.Configure(10, 10, false)) return 1;
  bool alternate = false;
  uint32_t previous_ms = to_ms_since_boot(get_absolute_time());
  while (true) {
    const uint32_t now_ms = to_ms_since_boot(get_absolute_time());
    const bool cadence_valid = uint32_t(now_ms - previous_ms) <= 10u;
    previous_ms = now_ms;
    if (!cadence_valid) control.Sample(0.0f, false);
    if (button.Observe(!gpio_get(15), now_ms, cadence_valid) && button.pressed()) {
      alternate = !alternate;
      control.ExternalEdit(alternate ? 0.75f : 0.25f);
    }
    // adc_read performs a fresh blocking conversion. Range checks do not detect
    // a disconnected wiper, wiring faults or every analogue acquisition error.
    const uint16_t raw = adc_read();
    control.Sample(static_cast<float>(raw) * 100.0f / 4095.0f, raw <= 4095u);
    gpio_put(PICO_DEFAULT_LED_PIN,
             control.state() == eurorack_patterns::PickupLatch::State::kTracking);
    sleep_ms(1); // Nominal polling cadence only; this is not a timing guarantee.
  }
}
