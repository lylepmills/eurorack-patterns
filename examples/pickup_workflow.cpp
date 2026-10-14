// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "shared_control.h"
#include <cstdio>

int main() {
  example::SharedControl control;
  if (!control.Reset(0.3f)) return 1;         // Preset owns the destination.
  if (control.Sample(80.0f, true)) return 1; // Seed the physical position.
  if (control.Sample(60.0f, true)) return 1;
  if (!control.Sample(20.0f, true)) return 1; // Crossed: knob now owns it.
  if (control.value() != 0.2f) return 1;

  if (!control.ExternalEdit(0.7f)) return 1; // New bank/preset/remote edit.
  control.Sample(0.0f, false);              // Acquisition gap, not zero volts.
  if (control.Sample(90.0f, true)) return 1; // Gap cannot imply a crossing.
  if (!control.Sample(60.0f, true)) return 1;
  if (!control.Reset(0.5f)) return 1;        // No previous owner/history survives.
  if (control.Sample(60.0f, true)) return 1;
  std::puts("PASS: initialization, takeover, filtering, invalid gap and reset");
}
