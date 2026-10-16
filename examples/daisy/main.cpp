// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "sys/system.h"
#include "dev/sdram.h"
#include "hid/usb.h"
#include "per/gpio.h"
#include "stm32h7xx_hal.h"
#include "usbd_cdc.h"
#include "build_identity.h"
#include "protocol.h"
#include "experiment.h"
#include <atomic>
#include <cstring>

using namespace daisy;
extern "C" USBD_HandleTypeDef hUsbDeviceFS;
static System system_hw;
static SdramHandle memory;
static UsbHandle usb;
static GPIO button_pin, sample_marker, action_marker, led;
static ADC_HandleTypeDef adc;
static DSY_SDRAM_BSS bench::Record records[bench::kMaxRecords];
static_assert(sizeof(records) <= 16 * 1024 * 1024, "Keep the trace buffer within its SDRAM budget");
static_assert(ATOMIC_INT_LOCK_FREE == 2, "USB IRQ mailbox requires lock-free 32-bit atomics");
static std::atomic<uint32_t> rx_head{0}, rx_tail{0}, rx_dropped{0};
static char rx[256];
static bool ready, startup_available;
struct CaptureState {
  uint32_t scenario, duration, target, count, missed, failures, overflow, elapsed, dropped;
  bool held;
  bench::Stimulus stimulus;
};
static CaptureState saved;

// USB IRQ only publishes bytes; all control/state/logging work has one owner.
static void Receive(uint8_t* bytes, uint32_t* size) {
  for (uint32_t i = 0; i < *size; ++i) {
    const uint32_t head = rx_head.load(std::memory_order_relaxed);
    if (head - rx_tail.load(std::memory_order_acquire) == sizeof(rx)) {
      rx_dropped.fetch_add(1, std::memory_order_relaxed);
    } else {
      rx[head % sizeof(rx)] = static_cast<char>(bytes[i]);
      rx_head.store(head + 1, std::memory_order_release);
    }
  }
}
static bool Read(char& c) {
  const uint32_t tail = rx_tail.load(std::memory_order_relaxed);
  if (tail == rx_head.load(std::memory_order_acquire)) return false;
  c = rx[tail % sizeof(rx)];
  rx_tail.store(tail + 1, std::memory_order_release);
  return true;
}
static bool TxIdle() {
  // A disconnect can replace the class pointer in the USB IRQ. Inspect the
  // pointer and its state atomically with respect to that IRQ.
  const uint32_t mask = __get_PRIMASK(); __disable_irq();
  volatile USBD_HandleTypeDef* device = &hUsbDeviceFS;
  auto* cdc = static_cast<USBD_CDC_HandleTypeDef*>(device->pClassData);
  const bool idle = device->dev_state == USBD_STATE_CONFIGURED && cdc && !cdc->TxState;
  __set_PRIMASK(mask);
  return idle;
}
static bool Send(const char* text) {
  // Stable storage is retained even on timeout. Never overwrite an in-flight
  // packet; SDK success means queued, not completed.
  static uint8_t tx[512];
  const size_t size = std::strlen(text);
  if (size > sizeof(tx)) return false;
  uint32_t start = System::GetNow();
  while (true) {
    bool queued = false;
    const uint32_t mask = __get_PRIMASK(); __disable_irq();
    if (TxIdle()) {
      std::memcpy(tx, text, size);
      queued = usb.TransmitInternal(tx, size) == UsbHandle::Result::OK;
    }
    __set_PRIMASK(mask);
    if (queued) break;
    if (uint32_t(System::GetNow() - start) > 5000) return false;
  }
  start = System::GetNow();
  while (!TxIdle()) if (uint32_t(System::GetNow() - start) > 5000) return false;
  return true;
}
static uint32_t AdcHz() {
  uint32_t hz = HAL_RCCEx_GetPeriphCLKFreq(RCC_PERIPHCLK_ADC) / 2;
  if (HAL_GetREVID() > REV_ID_Y) hz /= 2; // STM32H750 revision V internal divider.
  return hz;
}
static bool InitAdc() {
  // CPU-polled, single conversion: completion establishes sample freshness.
  // Do not use AdcHandle's background DMA/cache as a freshness indicator.
  __HAL_RCC_ADC12_CLK_ENABLE();
  __HAL_RCC_GPIOC_CLK_ENABLE();
  GPIO_InitTypeDef pin{};
  pin.Pin = GPIO_PIN_0; pin.Mode = GPIO_MODE_ANALOG; pin.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOC, &pin);
  adc.Instance = ADC1;
  adc.Init.ClockPrescaler = ADC_CLOCK_ASYNC_DIV2;
  adc.Init.Resolution = ADC_RESOLUTION_16B;
  adc.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
  adc.Init.NbrOfConversion = 1;
  adc.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  adc.Init.ConversionDataManagement = ADC_CONVERSIONDATA_DR;
  adc.Init.Overrun = ADC_OVR_DATA_OVERWRITTEN;
  adc.Init.LeftBitShift = ADC_LEFTBITSHIFT_NONE;
  adc.Init.OversamplingMode = DISABLE;
  if (HAL_ADC_Init(&adc) != HAL_OK ||
      HAL_ADCEx_Calibration_Start(&adc, ADC_CALIB_OFFSET_LINEARITY, ADC_SINGLE_ENDED) != HAL_OK)
    return false;
  ADC_ChannelConfTypeDef ch{};
  ch.Channel = ADC_CHANNEL_10; // PC0 / D15 / A0 / physical pin 22.
  ch.Rank = ADC_REGULAR_RANK_1;
  ch.SamplingTime = ADC_SAMPLETIME_810CYCLES_5; // Conservative 100k-pot starting point.
  ch.SingleDiff = ADC_SINGLE_ENDED;
  ch.OffsetNumber = ADC_OFFSET_NONE;
  return HAL_ADC_ConfigChannel(&adc, &ch) == HAL_OK;
}
static bool ReadAdc(uint16_t& raw) {
  raw = 0;
  bool ok = HAL_ADC_Start(&adc) == HAL_OK;
  if (ok) ok = HAL_ADC_PollForConversion(&adc, 2) == HAL_OK;
  if (ok) raw = static_cast<uint16_t>(HAL_ADC_GetValue(&adc));
  if (HAL_ADC_Stop(&adc) != HAL_OK) ok = false;
  return ok;
}
static void Identity() {
  char line[512];
  std::snprintf(line, sizeof(line),
      "INFO,{\"protocol\":2,\"build_id\":\"%s\",\"board\":\"seed3\",\"ready\":%s,"
      "\"cpu_hz\":%u,\"timer_hz\":%u,\"adc_hz\":%u,\"mcu_revision\":%u,\"sample_cycles_x2\":1621,"
      "\"oversampling\":1,\"period_us\":1000,\"max_records\":%u,\"startup_available\":%s,\"startup_duration_ms\":%u}\n",
      EP_BUILD_ID, ready ? "true" : "false", unsigned(SystemCoreClock),
      unsigned(System::GetTickFreq()), unsigned(AdcHz()), unsigned(HAL_GetREVID()),
      unsigned(bench::kMaxRecords), startup_available ? "true" : "false", unsigned(bench::kStartupDurationMs));
  Send(line);
}
static bool StartLine(uint32_t token) {
  char line[128];
  std::snprintf(line, sizeof(line), "START,%u,%u,%u,%u,%u\n", unsigned(token),
                unsigned(saved.scenario), unsigned(saved.duration), unsigned(saved.target), unsigned(saved.held));
  return Send(line);
}
static void Collect() {
  const uint32_t scenario = saved.scenario, duration = saved.duration, target = saved.target;
  const bool held = saved.held;
  bench::Experiment experiment(scenario, held);
  bench::Controls controls;
  controls.Reset(target, held);
  bench::Clock clock(System::GetTick(), System::GetTickFreq());
  bench::Schedule schedule;
  uint32_t count = 0, missed = 0, failures = 0, overflow = 0;
  const uint32_t rx_before = rx_dropped.load();
  bool action_level = false;
  uint32_t target_epoch = 0;
  action_marker.Write(false);
  while (true) {
    uint32_t us = clock.Us(System::GetTick());
    if (us >= duration * 1000) break;
    const uint32_t stall_ms = experiment.Stall(us);
    if (stall_ms) {
      System::Delay(stall_ms);
      us = clock.Us(System::GetTick());
      experiment.EndStall(us);
    }
    if (us >= duration * 1000) break;
    if (!schedule.Due(us)) continue;
    if (count == bench::kMaxRecords) { ++overflow; break; }
    sample_marker.Write(true);
    us = clock.Us(System::GetTick());
    if (us >= duration * 1000) { sample_marker.Write(false); break; }
    missed += schedule.Take(us);
    const bool pressed = !button_pin.Read();
    const bool injected = experiment.InvalidAdc(us);
    uint16_t raw = 0;
    const uint32_t adc_start = clock.Us(System::GetTick());
    const bool valid = !injected && ReadAdc(raw);
    const uint32_t adc_us = clock.Us(System::GetTick()) - adc_start;
    if (!valid && !injected) ++failures;
    int32_t external = experiment.Observe(us, raw, valid, pressed);
    if (scenario == 1 && us / 5000000 != target_epoch) {
      target_epoch = us / 5000000;
      external = (target_epoch % 2) ? 750 : 250;
    }
    const auto result = controls.Step(us, raw, valid, pressed, external);
    if (result.gesture) { action_level = !action_level; action_marker.Write(action_level); }
    led.Write(result.state == 2);
    if (scenario == 4) {
      const uint32_t load_start = clock.Us(System::GetTick());
      // Deliberate foreground CPU occupancy, not a model of audio/IRQ load.
      while (clock.Us(System::GetTick()) - load_start < 400) __NOP();
    }
    records[count] = {count, us, adc_us, 0, raw, valid, injected, pressed,
                      external, result, missed};
    records[count].work_us = clock.Us(System::GetTick()) - us;
    sample_marker.Write(false);
    ++count;
  }
  saved.elapsed = clock.Us(System::GetTick());
  saved.dropped = rx_dropped.load() - rx_before;
  saved.count = count; saved.missed = missed; saved.failures = failures; saved.overflow = overflow;
  saved.stimulus = experiment.stimulus();
  sample_marker.Write(false);
}
static bool Download(uint32_t token) {
  char line[512];
  // No formatting or USB transmission occurs inside the acquisition loop.
  std::snprintf(line, sizeof(line), "STIMULUS,%d,%d,%d\n", int(saved.stimulus.trigger),
                int(saved.stimulus.begin), int(saved.stimulus.end));
  if (!Send(line)) return false;
  uint32_t hash = bench::Hash(2166136261u, line, std::strlen(line));
  std::snprintf(line, sizeof(line), "COLUMNS,%s\n", bench::kColumns);
  if (!Send(line)) return false;
  for (uint32_t i = 0; i < saved.count; ++i) {
    const int n = bench::FormatRecord(line, sizeof(line), records[i]);
    if (n < 0 || size_t(n) >= sizeof(line)) { Send("ERROR,format\n"); return false; }
    hash = bench::Hash(hash, line, size_t(n));
    if (!Send(line)) return false;
  }
  std::snprintf(line, sizeof(line), "END,%u,%u,%u,%u,%u,%u,%u,%u\n", unsigned(token),
      unsigned(saved.count), unsigned(saved.missed), unsigned(saved.failures), unsigned(saved.dropped),
      unsigned(saved.overflow), unsigned(hash), unsigned(saved.elapsed));
  return Send(line);
}
static void Run(uint32_t token, uint32_t scenario, uint32_t duration, uint32_t target) {
  saved = {};
  saved.scenario = scenario; saved.duration = duration; saved.target = target;
  saved.held = !button_pin.Read();
  if (!StartLine(token)) return;
  // Host cue only; D0, not START reception, is the acquisition timing reference.
  System::Delay(50);
  Collect();
  Download(token);
}
int main() {
  // No codec/audio, QSPI erase/program, persistent settings or bootloader calls.
  const bool old_boot = System::GetBootloaderVersion() == System::BootInfo::Version::LT_v6_0;
  System::Config cfg; cfg.Boost(); cfg.skip_clocks = old_boot;
  system_hw.Init(cfg);
  ready = old_boot || memory.Init() == SdramHandle::Result::OK;
  button_pin.Init(Pin(PORTB, 7), GPIO::Mode::INPUT, GPIO::Pull::PULLUP);
  sample_marker.Init(Pin(PORTB, 12), GPIO::Mode::OUTPUT);
  action_marker.Init(Pin(PORTC, 11), GPIO::Mode::OUTPUT);
  led.Init(Pin(PORTC, 7), GPIO::Mode::OUTPUT);
  sample_marker.Write(false); action_marker.Write(false); led.Write(false);
  ready = ready && InitAdc();
  // Automatic post-initialization capture. USB is deliberately initialized only
  // afterward, so neither host enumeration nor a command defines startup state.
  // This does not cover ROM/bootloader, clock/RAM/ADC initialization or rail rise.
  if (ready) {
    saved = {};
    saved.scenario = bench::kStartup; saved.duration = bench::kStartupDurationMs;
    saved.target = 250; saved.held = !button_pin.Read();
    Collect();
    startup_available = true;
  }
  usb.Init(UsbHandle::FS_INTERNAL);
  usb.SetReceiveCallback(Receive, UsbHandle::FS_INTERNAL);
  char command[96]; size_t used = 0; bool too_long = false;
  while (true) {
    char c;
    if (!Read(c)) continue;
    if (c == '\r') continue;
    if (c != '\n') {
      if (used + 1 < sizeof(command)) command[used++] = c;
      else too_long = true;
      continue;
    }
    command[used] = '\0';
    if (too_long) Send("ERROR,command_length\n");
    else if (std::strcmp(command, "?") == 0) Identity();
    else {
      unsigned token, scenario, duration, target; char extra;
      if (ready && std::sscanf(command, "B,%u%c", &token, &extra) == 1) {
        if (!startup_available) Send("ERROR,no_startup_capture\n");
        else if (StartLine(token) && Download(token)) startup_available = false;
      } else if (ready && std::sscanf(command, "R,%u,%u,%u,%u%c", &token, &scenario, &duration,
                                      &target, &extra) == 4 && scenario <= bench::kMovingTarget &&
                 duration >= 1000 && duration <= bench::kMaxDurationMs && target <= 1000 &&
                 (!(scenario >= bench::kPickupGapUp && scenario <= bench::kMovingTarget) || target == 250)) {
        if (startup_available) Send("ERROR,download_startup_first\n");
        else Run(token, scenario, duration, target);
      } else Send("ERROR,command_or_not_ready\n");
    }
    used = 0; too_long = false;
  }
}
