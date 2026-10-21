// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
// Seed3 SAI pin/configuration setup adapted from libDaisy DaisySeed::ConfigureAudio,
// e1f740a5a7fe38e6d6d41281bf99fe7a2bb3827b, Copyright (c) 2019 Electrosmith.
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.
#ifndef EP_DAISY_AUDIO_LOAD_H_
#define EP_DAISY_AUDIO_LOAD_H_
#include "hid/audio.h"
#include "dev/codec_ak4556.h"
#include "sys/system.h"
#include <algorithm>
#include <atomic>

namespace audio_load {
#ifndef EP_AUDIO_MARKER
#define EP_AUDIO_MARKER(value) ((void)0)
#endif
#ifndef EP_AUDIO_WORK_CLOCK
#define EP_AUDIO_WORK_CLOCK() daisy::System::GetTick()
#endif
struct Counters {
  uint32_t callbacks = 0, max_work_ticks = 0, max_interval_ticks = 0;
  uint32_t over_budget = 0, late_intervals = 0, bad_size = 0;
};
static daisy::AudioHandle audio;
static daisy::SaiHandle sai;
static daisy::Ak4556 codec;
static bool initialized = false;
static std::atomic<bool> measuring{false};
// IRQ owns these fields while measuring. Foreground resets/snapshots with IRQs
// masked, and never changes configuration while audio is running.
static Counters counters;
static uint32_t previous_tick, period_ticks, busy_ticks, block_size;

static void Callback(daisy::AudioHandle::InputBuffer, daisy::AudioHandle::OutputBuffer out, size_t size) {
  const bool measure = measuring.load(std::memory_order_relaxed);
  // Keep timestamp/marker pairs together even when acquisition can preempt
  // audio. Only bookkeeping is masked; silence/padding runs with IRQs enabled.
  const uint32_t start_guard = __get_PRIMASK(); __disable_irq();
  const uint32_t start = daisy::System::GetTick();
  const uint32_t work_start = EP_AUDIO_WORK_CLOCK();
  if (measure) EP_AUDIO_MARKER(true);
  __set_PRIMASK(start_guard);
  // Silence on both channels. This tests scheduling, not codec audio quality.
  for (size_t i = 0; i < size; ++i) out[0][i] = out[1][i] = 0.0f;
  while (uint32_t(EP_AUDIO_WORK_CLOCK() - work_start) < busy_ticks) __NOP();
  if (!measure) return;
  const uint32_t end_guard = __get_PRIMASK(); __disable_irq();
  const uint32_t work = daisy::System::GetTick() - start;
  if (counters.callbacks) {
    const uint32_t interval = start - previous_tick;
    counters.max_interval_ticks = std::max(counters.max_interval_ticks, interval);
    counters.late_intervals += interval > period_ticks * 3 / 2;
  }
  previous_tick = start;
  ++counters.callbacks;
  counters.max_work_ticks = std::max(counters.max_work_ticks, work);
  counters.over_budget += work >= period_ticks;
  counters.bad_size += size != block_size;
  EP_AUDIO_MARKER(false);
  __set_PRIMASK(end_guard);
}
static bool Start(uint32_t block, uint32_t permille) {
  if (!initialized) {
    daisy::GPIO board;
    board.Init(daisy::Pin(daisy::PORTH, 6), daisy::GPIO::Mode::INPUT, daisy::GPIO::Pull::PULLUP);
    if (board.Read()) return false; // This configuration is for Seed3 only.
    daisy::SaiHandle::Config cfg;
    cfg.periph = daisy::SaiHandle::Config::Peripheral::SAI_1;
    cfg.sr = daisy::SaiHandle::Config::SampleRate::SAI_48KHZ;
    cfg.bit_depth = daisy::SaiHandle::Config::BitDepth::SAI_24BIT;
    cfg.a_sync = daisy::SaiHandle::Config::Sync::MASTER;
    cfg.b_sync = daisy::SaiHandle::Config::Sync::SLAVE;
    cfg.a_dir = daisy::SaiHandle::Config::Direction::TRANSMIT;
    cfg.b_dir = daisy::SaiHandle::Config::Direction::RECEIVE;
    cfg.pin_config.fs = daisy::Pin(daisy::PORTE, 4);
    cfg.pin_config.mclk = daisy::Pin(daisy::PORTE, 2);
    cfg.pin_config.sck = daisy::Pin(daisy::PORTE, 5);
    cfg.pin_config.sa = daisy::Pin(daisy::PORTE, 6);
    cfg.pin_config.sb = daisy::Pin(daisy::PORTE, 3);
    codec.Init(daisy::Pin(daisy::PORTB, 11));
    if (sai.Init(cfg) != daisy::SaiHandle::Result::OK) return false;
    daisy::AudioHandle::Config ac;
    ac.blocksize = block;
    if (audio.Init(ac, sai) != daisy::AudioHandle::Result::OK) return false;
    initialized = true;
  }
  block_size = block;
  period_ticks = uint32_t(uint64_t(daisy::System::GetTickFreq()) * block / 48000);
  busy_ticks = uint32_t(uint64_t(period_ticks) * permille / 1000);
  if (audio.SetBlockSize(block) != daisy::AudioHandle::Result::OK) return false;
  return audio.Start(Callback) == daisy::AudioHandle::Result::OK;
}
static void Stop() {
  if (initialized) audio.Stop();
}
} // namespace audio_load
#endif
