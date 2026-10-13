// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
// Synthetic trace: partial insertion and contact chatter versus sustained jack.
static const char kPresenceChatterTrace[] = R"TRACE(
config 4 2 3 first known 0
match 4
mismatch 1
match 3
expect 1 0 2 0 0
mismatch 8
expect 1 0 4 2 0
match 4
expect 1 0 5 0 0
mismatch 12
expect 1 1 8 3 0
invalid 1
expect 1 1 8 0 0
match 4
expect 1 0 9 0 0
)TRACE";
