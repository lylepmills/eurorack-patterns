// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EP_DAISY_DMA_WORKLOAD_H_
#define EP_DAISY_DMA_WORKLOAD_H_
#include "stm32h7xx_hal.h"
#include "sys/system.h"
#include "dev/sdram.h"
#include "dsp_workload.h"
#include "dma_config.h"
#include <atomic>

// Own DMA2 stream 6 exclusively. Source and destination are disjoint, complete
// 32-byte cache lines in the selected SDRAM or AXI SRAM region. CPU writes source only before clean/start and
// reads destination only after completion/invalidate (ST AN4839). No peripheral
// polling, cache maintenance, or data verification is performed in the IRQ.
namespace dmabench {
struct alignas(32) Buffers { uint32_t source[4096], destination[4096]; };
struct alignas(32) Arena { uint32_t words[dmaconfig::kArenaBytes / 4]; };
static_assert(sizeof(Buffers) == 2 * dmaconfig::kBufferBytes, "DMA buffer layout");
extern "C" {
// Stable symbols let the builder verify placement in the final ELF, not just
// trust a source annotation. Both choices coexist in the same firmware image.
__attribute__((section(".ep_dma_internal"), used)) Buffers ep_dma_internal_buffers;
__attribute__((section(".ep_dma_sdram"), used)) Buffers ep_dma_sdram_buffers;
__attribute__((section(".ep_dma_low_arena"), used)) Arena ep_dma_low_arena;
__attribute__((section(".ep_dma_high_arena"), used)) Arena ep_dma_high_arena;
}
static uint32_t* source = nullptr;
static uint32_t* destination = nullptr;
static DMA_HandleTypeDef handle;
static std::atomic<uint32_t> event{0}; // 0 pending, 1 complete, 2 peripheral error
static uint32_t completion_tick, irq_count, max_irq_ticks;
struct Counters {
  uint32_t started = 0, completed = 0, verified = 0, bytes = 0;
  uint32_t errors = 0, corrupt_words = 0, timeouts = 0, skipped = 0;
  uint32_t first_us = 0, last_us = 0, max_gap_us = 0, max_transfer_ticks = 0;
};
static Counters counters;
static uint32_t words, next_us, start_tick, period_us;
static bool pending = false;
static void Complete(DMA_HandleTypeDef*) {
  completion_tick = daisy::System::GetTick(); event.store(1, std::memory_order_release);
}
static void Error(DMA_HandleTypeDef*) { event.store(2, std::memory_order_release); }
static bool Reset(uint32_t kib, uint32_t region, uint32_t requested_period_us) {
  if (!dmaconfig::ValidPlan(kib, region, requested_period_us)) return false;
  counters = {}; event.store(0); irq_count = max_irq_ticks = 0;
  words = kib * 256; pending = false; period_us = requested_period_us; next_us = period_us;
  source = destination = nullptr;
  if (!kib) return true;
  // Selection happens once before acquisition. Every run shares the same hot
  // transfer/cache/verification code; no alignment-dependent branch in Service.
  if (region < 2) {
    auto& buffers = region == 1 ? ep_dma_internal_buffers : ep_dma_sdram_buffers;
    source = buffers.source; destination = buffers.destination;
  } else {
    auto& arena = dmaconfig::LowArena(region) ? ep_dma_low_arena : ep_dma_high_arena;
    source = arena.words + dmaconfig::Offset(region) / 4;
    destination = source + dmaconfig::kBufferBytes / 4;
  }
  if (!dmaconfig::ValidBuffers(region, uint32_t(source), uint32_t(destination))) return false;
  __HAL_RCC_DMA2_CLK_ENABLE();
  handle.Instance = DMA2_Stream6;
  handle.Init.Request = DMA_REQUEST_MEM2MEM;
  handle.Init.Direction = DMA_MEMORY_TO_MEMORY;
  handle.Init.PeriphInc = DMA_PINC_ENABLE; handle.Init.MemInc = DMA_MINC_ENABLE;
  handle.Init.PeriphDataAlignment = DMA_PDATAALIGN_WORD;
  handle.Init.MemDataAlignment = DMA_MDATAALIGN_WORD;
  handle.Init.Mode = DMA_NORMAL; handle.Init.Priority = DMA_PRIORITY_LOW;
  handle.Init.FIFOMode = DMA_FIFOMODE_ENABLE;
  handle.Init.FIFOThreshold = DMA_FIFO_THRESHOLD_FULL;
  handle.Init.MemBurst = DMA_MBURST_INC4; handle.Init.PeriphBurst = DMA_PBURST_INC4;
  if (HAL_DMA_Init(&handle) != HAL_OK) return false;
  handle.XferCpltCallback = Complete; handle.XferErrorCallback = Error;
  HAL_NVIC_SetPriority(DMA2_Stream6_IRQn, 2, 0);
  NVIC_ClearPendingIRQ(DMA2_Stream6_IRQn); HAL_NVIC_EnableIRQ(DMA2_Stream6_IRQn);
  return true;
}
static bool Service(uint32_t us, bool allow_start) {
  if (!words) return true;
  if (pending) {
    const uint32_t result = event.load(std::memory_order_acquire);
    if (result == 2) { ++counters.errors; return false; }
    if (!result) {
      if (uint32_t(daisy::System::GetTick() - start_tick) > daisy::System::GetTickFreq()/200) {
        ++counters.timeouts; return false; // bounded 5ms transfer, never busy-wait in IRQ
      }
      return true;
    }
    const uint32_t work = completion_tick - start_tick;
    counters.max_transfer_ticks = std::max(counters.max_transfer_ticks, work);
    ++counters.completed;
    SCB_InvalidateDCache_by_Addr(destination, int32_t(words * 4));
    for (uint32_t i = 0; i < words; ++i)
      counters.corrupt_words += destination[i] != dspbench::Word(counters.started, i);
    if (counters.corrupt_words) return false;
    ++counters.verified; counters.bytes += words * 4;
    if (!counters.first_us) counters.first_us = us;
    if (counters.last_us) counters.max_gap_us = std::max(counters.max_gap_us, us - counters.last_us);
    counters.last_us = us; pending = false;
  }
  if (!allow_start || us < next_us) return true;
  // Do not accumulate a queue or catch up after foreground starvation.
  counters.skipped += (us - next_us) / period_us;
  next_us = (us / period_us + 1) * period_us;
  ++counters.started;
  for (uint32_t i = 0; i < words; ++i) source[i] = dspbench::Word(counters.started, i);
  SCB_CleanDCache_by_Addr(source, int32_t(words * 4));
  SCB_CleanInvalidateDCache_by_Addr(destination, int32_t(words * 4));
  event.store(0, std::memory_order_relaxed);
  start_tick = daisy::System::GetTick(); pending = true;
  if (HAL_DMA_Start_IT(&handle, uint32_t(source), uint32_t(destination), words) != HAL_OK) {
    ++counters.errors; return false;
  }
  return true;
}
static void Stop() {
  if (!words) return;
  HAL_NVIC_DisableIRQ(DMA2_Stream6_IRQn);
  if (pending) HAL_DMA_Abort(&handle);
  NVIC_ClearPendingIRQ(DMA2_Stream6_IRQn);
}
} // namespace dmabench
extern "C" void DMA2_Stream6_IRQHandler() {
  const uint32_t tick = daisy::System::GetTick();
  HAL_DMA_IRQHandler(&dmabench::handle);
  ++dmabench::irq_count;
  dmabench::max_irq_ticks = std::max(dmabench::max_irq_ticks, daisy::System::GetTick() - tick);
}
#endif
