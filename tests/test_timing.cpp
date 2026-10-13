// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include <eurorack_patterns/timing.h>
#include <cstdio>
#include <cstdlib>
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x); std::exit(1); } } while (0)
int main() {
  eurorack_patterns::DebouncedButton button;
  CHECK(!button.Observe(true,100));
  CHECK(button.Configure(10,3));
  CHECK(!button.Observe(true,100));
  CHECK(!button.Observe(false,105)); // bounce cancels earlier candidate
  CHECK(!button.Observe(true,107));
  CHECK(!button.Observe(true,116));
  CHECK(button.Observe(true,117));
  CHECK(button.pressed());
  CHECK(!button.Observe(true,118)); // one event per transition
  CHECK(!button.Observe(false,119));
  CHECK(button.Observe(false,122));
  CHECK(!button.pressed());
  CHECK(!button.Observe(true,125));
  CHECK(!button.Observe(true,140,false));
  CHECK(!button.Observe(true,150)); // no accumulation through invalid gap
  CHECK(button.Observe(true,160));
  CHECK(!button.Configure(0x80000000u,0));
  CHECK(button.pressed()); // rejected config leaves existing state
  CHECK(button.Configure(10,3));
  CHECK(!button.Observe(true,0xfffffffau));
  CHECK(!button.Observe(true,3));
  CHECK(button.Observe(true,4)); // wrap without signed arithmetic
  CHECK(button.Configure(0,0,true));
  CHECK(!button.Observe(true,0));
  CHECK(button.Observe(false,0));
  CHECK(button.Observe(true,0));
  std::puts("PASS: debounce bounce, asymmetry, invalid gaps, wrap, zero duration");
}
