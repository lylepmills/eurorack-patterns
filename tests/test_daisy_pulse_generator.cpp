// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "../examples/daisy/pulse_generator.h"
#include <cstdio>
#include <cstdlib>
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)
int main() {
  pulsegen::Plan plan;
  CHECK(pulsegen::ParsePlan("P,4294967295,4,100000,200000,300000,400000", plan));
  CHECK(plan.token == UINT32_MAX && plan.Valid());
  const char* invalid[] = {"", "P", "P,", "P,0", "P,0,", "P,0,0", "P,0,65",
    "P,-1,2,100000,200000", "P,4294967296,2,100000,200000",
    "P,0,2,99999,200000", "P,0,2,100000,100099", "P,0,2,100000,100000",
    "P,0,2,100001,100000", "P,0,2,100000,30000001", "P,0,3,100000,200000,300000",
    "P,0,2,100000,200000,", "P,0,2,100000,200000x", "P,0,2,100000, 200000",
    "P,0,2,100000,4294967296", "P,0,2,100000", "P,0,2,100000,"};
  for (const auto* text : invalid) {
    CHECK(!pulsegen::ParsePlan(text, plan));
    CHECK(plan.token == UINT32_MAX && plan.count == 4); // transactional parse
  }
  uint32_t token = 0;
  CHECK(pulsegen::ParseRun("R,4294967295", token) && token == UINT32_MAX);
  CHECK(!pulsegen::ParseRun("R,-1", token)); CHECK(!pulsegen::ParseRun("R,0,", token));
  CHECK(!pulsegen::ParseRun("", token)); CHECK(!pulsegen::ParseRun("R", token));
  bool pressed = false;
  pulsegen::Sequence run(plan);
  CHECK(run.Poll(99999, pressed) == pulsegen::Sequence::kWaiting && !pressed);
  CHECK(run.Poll(100025, pressed) == pulsegen::Sequence::kEdge && pressed);
  CHECK(run.Poll(199999, pressed) == pulsegen::Sequence::kWaiting && pressed);
  CHECK(run.Poll(200000, pressed) == pulsegen::Sequence::kEdge && !pressed);
  CHECK(run.Poll(300026, pressed) == pulsegen::Sequence::kLate && !pressed);
  CHECK(run.Poll(400000, pressed) == pulsegen::Sequence::kLate && run.count() == 2);
  pulsegen::Sequence complete(plan);
  for (uint32_t i = 0; i < plan.count; ++i) {
    CHECK(complete.Poll(plan.times[i], pressed) == pulsegen::Sequence::kEdge);
    CHECK(pressed == (i % 2 == 0));
  }
  CHECK(complete.Poll(400001, pressed) == pulsegen::Sequence::kDone && !pressed);
  CHECK(pulsegen::ParsePlan("P,0,2,100000,30000000", plan));
  std::puts("PASS: bounded pulse plans, strict commands, late-abort without catch-up");
}
