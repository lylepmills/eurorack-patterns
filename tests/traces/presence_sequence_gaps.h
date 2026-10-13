// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
// Synthetic trace: adapter marks missing and duplicate frames invalid. These
// labels represent adapter decisions, never fresh ADC evidence.
static const char kPresenceSequenceGapsTrace[] = R"TRACE(
config 4 2 3 streak unknown 0
mismatch 4
expect 0 0 1 1 0
missing 1
expect 0 0 1 0 0
mismatch 4
expect 0 0 2 1 0
duplicate 1
expect 0 0 2 0 0
mismatch 8
expect 0 0 4 2 0
mismatch 4
expect 1 1 5 3 0
missing 1
expect 1 1 5 0 0
match 4
expect 1 0 6 0 0
)TRACE";
