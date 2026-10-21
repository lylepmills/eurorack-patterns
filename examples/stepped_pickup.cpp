// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "stepped_control.h"
#include <cstdio>

namespace {
struct Parameter {
  float stored = 0.5f;
  float ReadNormalized() const { return stored; }
  void WriteNormalized(float requested) {
    // Called only with finite [0,1] input. Double arithmetic avoids rounding a
    // float just below a midpoint onto that midpoint before the integer cast.
    const int step = static_cast<int>(static_cast<double>(requested) * 4.0 + 0.5);
    stored = static_cast<float>(step) * 0.25f;
  }
};
}  // namespace

int main() {
  Parameter destination;
  example::SteppedControl<Parameter> control(destination);
  using Result = example::SteppedControl<Parameter>::WriteResult;
  using State = example::SteppedControl<Parameter>::State;
  if (control.Sample(0.1f, true) != Result::kNone) return 1;
  // .44 snaps to the stored .5 step: pickup precedes the raw .5 position.
  if (control.Sample(0.44f, true) != Result::kMatched) return 1;
  if (control.value() != 0.5f || control.state() != State::kTracking) return 1;
  if (control.Sample(0.8f, true) != Result::kMatched) return 1;
  if (control.value() != 0.75f) return 1;  // Show readback, not the .8 request.

  destination.stored = 0.4f;  // An incompatible saved value; no silent repair.
  if (control.Rearm() || control.state() != State::kUnreachable) return 1;
  if (control.Sample(1.0f, true) != Result::kNone) return 1;
  if (control.value() != 0.4f) return 1;
  destination.stored = 0.5f;  // Explicit recovery by the preset/UI owner.
  if (!control.Rearm()) return 1;
  if (control.Sample(0.0f, true) != Result::kNone) return 1;
  if (control.Sample(0.0f, false) != Result::kNone) return 1;
  if (control.Sample(1.0f, true) != Result::kNone) return 1;
  if (control.Sample(0.0f, true) != Result::kMatched) return 1;
  std::puts("PASS: stepped pickup, readback, unreachable recovery and invalid gap");
}
