// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
// Synthetic trace: several acquired pulses before a slow consume, saturation
// with a latched overflow, and explicit reset/reacquisition behavior.
static const char kEventsSaturationTrace[] = R"TRACE(
config 1 3 2 count
sample 3 1
expect 1 0 1 1
sample 0 1
sample 3 1
expect 2 0 1 1
sample 0 1
sample 3 1
expect 2 1 1 1
consume 1 1
expect 1 1 1 1
sample 0 1
sample 3 1
expect 2 1 1 1
consume 2 2
expect 0 1 1 1
clear_overflow
expect 0 0 1 1
invalid 1
sample 2 1
expect 0 0 0 0
sample 3 1
expect 1 0 1 1
reset
expect 0 0 0 0
)TRACE";
