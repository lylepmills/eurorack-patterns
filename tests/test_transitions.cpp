// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include <eurorack_patterns/transitions.h>
#include <cstdio>
#include <cstdlib>
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr,"%s:%d: %s\n",__FILE__,__LINE__,#x); std::exit(1); } } while (0)
int main() {
  eurorack_patterns::LatestRequest<int> requests;
  int active=7, pending=-1;
  CHECK(!requests.Take(active) && active==7);
  requests.Request(11);
  CHECK(requests.Take(active) && active==11); // transition starts
  for (int n=12;n<100000;++n) requests.Request(n); // UI keeps moving while busy
  CHECK(active==11 && requests.pending());
  CHECK(requests.Peek(pending) && pending==99999 && requests.pending());
  CHECK(requests.Take(active) && active==99999); // next safe boundary
  CHECK(!requests.Take(active) && active==99999);
  requests.Request(22); requests.Cancel();
  CHECK(!requests.pending() && !requests.Take(active) && active==99999);
  requests.Request(0); CHECK(requests.Take(active) && active==0);
  std::puts("PASS: latest destination, burst replacement, explicit commit and cancel");
}
