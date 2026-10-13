// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
// Synthetic trace: startup invalid data, first-window decision, unplug/reinsert.
static const char kPresenceStartupTrace[] = R"TRACE(
config 4 2 3 first unknown 0
expect 0 0 0 0 0
invalid 3
mismatch 3
expect 0 0 0 0 3
invalid 1
expect 0 0 0 0 0
match 2
mismatch 2
expect 1 1 1 1 0
match 4
expect 1 0 2 0 0
mismatch 8
expect 1 0 4 2 0
mismatch 4
expect 1 1 5 3 0
)TRACE";
