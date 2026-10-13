// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
// Synthetic trace: slow/noisy crossing, invalid acquisition, slower consumer.
static const char kEventsThresholdsTrace[] = R"TRACE(
config 1 3 4 silent
sample 2 1
expect 0 0 0 0
sample 0 1
sample 3 1
sample 2 3
expect 1 0 1 1
sample 1 1
sample 2 1
sample 3 1
expect 2 0 1 1
consume 1 1
invalid 1
expect 1 0 0 0
sample 3 1
expect 1 0 1 1
sample 0 1
sample 3 1
expect 2 0 1 1
)TRACE";
