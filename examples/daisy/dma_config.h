// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EP_DAISY_DMA_CONFIG_H_
#define EP_DAISY_DMA_CONFIG_H_
#include <cstdint>

namespace dmaconfig {
constexpr uint32_t kBufferBytes = 16384, kCacheLineBytes = 32;
constexpr uint32_t kArenaBytes = 65536;
// 0/1 retain the original SDRAM/AXI pairs. 2 retains the old high pair.
// 3/4, 5/6, 7/8 and 9/2 select matching low/high offsets 0,32,1024,0x7400.
inline bool LowArena(uint32_t region) { return region >= 3 && (region & 1u); }
inline uint32_t Offset(uint32_t region) {
  return region == 2 || region == 9 ? 0x7400u :
         region == 5 || region == 6 ? 32u : region == 7 || region == 8 ? 1024u : 0u;
}
inline uint32_t ArenaBase(uint32_t region) {
  return LowArena(region) ? 0xc0210000u : 0xc1d70000u;
}
inline bool ValidPlan(uint32_t kib, uint32_t region, uint32_t period_us) {
  return (kib == 0 || kib == 4 || kib == 16) && region <= 9 &&
         (period_us == 1000 || period_us == 2000) &&
         (kib || (region == 0 && period_us == 1000));
}
inline bool ValidBuffers(uint32_t region, uint32_t source, uint32_t destination) {
  if (region > 9 || source % kCacheLineBytes || destination % kCacheLineBytes) return false;
  if (region >= 2 && (source != ArenaBase(region) + Offset(region) ||
                     destination != source + kBufferBytes)) return false;
  const uint32_t begin = region == 1 ? 0x24000000u : 0xc0000000u;
  // The upper 32 KiB of AXI SRAM belong to the bootloader, not this app.
  const uint32_t end = region == 1 ? 0x24078000u : 0xc4000000u;
  return source >= begin && source <= end - kBufferBytes &&
         destination >= begin && destination <= end - kBufferBytes &&
         (source + kBufferBytes <= destination || destination + kBufferBytes <= source);
}
} // namespace dmaconfig
#endif
