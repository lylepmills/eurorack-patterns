// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EP_DAISY_PROTOCOL_H_
#define EP_DAISY_PROTOCOL_H_
#include "bench.h"
#include <cstdio>
namespace bench {
constexpr const char* kColumns = "seq,time_us,adc_us,work_us,raw,adc_valid,injected,pressed,external_milli,cadence_valid,accepted_ppm,value_ppm,target_ppm,state,debounced,gesture,changed,actions,missed";
inline int FormatRecord(char* out, size_t size, const Record& r) {
  return std::snprintf(out, size,
      "D,%u,%u,%u,%u,%u,%u,%u,%u,%d,%u,%d,%d,%d,%u,%u,%u,%u,%u,%u\n",
      unsigned(r.seq), unsigned(r.time_us), unsigned(r.adc_us), unsigned(r.work_us),
      unsigned(r.raw), unsigned(r.adc_valid), unsigned(r.injected), unsigned(r.pressed),
      int(r.external_milli), unsigned(r.result.cadence_valid), int(r.result.accepted_ppm),
      int(r.result.value_ppm), int(r.result.target_ppm), unsigned(r.result.state),
      unsigned(r.result.debounced), unsigned(r.result.gesture), unsigned(r.result.changed),
      unsigned(r.result.actions), unsigned(r.missed));
}
inline uint32_t Hash(uint32_t hash, const char* bytes, size_t size) {
  for (size_t i = 0; i < size; ++i) { hash ^= uint8_t(bytes[i]); hash *= 16777619u; }
  return hash;
}
} // namespace bench
#endif
