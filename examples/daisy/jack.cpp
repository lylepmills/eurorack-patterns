// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "sys/system.h"
#include "dev/sdram.h"
#include "hid/usb.h"
#include "per/gpio.h"
#include "stm32h7xx_hal.h"
#include "usbd_cdc.h"
#include "build_identity.h"
#include "jack_acquisition.h"
#include "protocol.h"
#include <atomic>
#include <cstring>
using namespace daisy;
extern "C" USBD_HandleTypeDef hUsbDeviceFS;
static System system_hw;
static SdramHandle memory;
static UsbHandle usb;
static GPIO probe_pin, sample_marker, presence_marker;
static GPIO audio_marker, diagnostic_audio_marker;
static bool clock_diagnostic;
static bool clock_output_active;
static uint32_t saved_mco2;
// Diagnostic only: expose the hardware HSE clock through MCO2 on the existing
// PC9 marker pin. No ISR toggles this waveform. Restore GPIO-low after each run.
static void ClockOutput(bool enable) {
  if (enable) {
    diagnostic_audio_marker.Write(false); // D4 / physical pin 5, diagnostic only.
    saved_mco2 = RCC->CFGR & (RCC_CFGR_MCO2 | RCC_CFGR_MCO2PRE);
    // Select the divider while PC9 is still GPIO-low; the HAL configures the
    // alternate-function pin before updating CFGR, which could expose an old
    // clock selection briefly if called alone.
    __HAL_RCC_MCO2_CONFIG(RCC_MCO2SOURCE_HSE, RCC_MCODIV_15);
    HAL_RCC_MCOConfig(RCC_MCO2, RCC_MCO2SOURCE_HSE, RCC_MCODIV_15);
    clock_output_active = true;
  } else if (clock_output_active) {
    audio_marker.Write(false);
    audio_marker.Init(Pin(PORTC, 9), GPIO::Mode::OUTPUT);
    audio_marker.Write(false);
    MODIFY_REG(RCC->CFGR, RCC_CFGR_MCO2 | RCC_CFGR_MCO2PRE, saved_mco2);
    diagnostic_audio_marker.Write(false);
    clock_output_active = false;
  }
}
static uint64_t acquisition_work_ticks;
// Read the counter and wall clock together; only acquisition IRQs change it.
// The audio busy loop excludes measured acquisition work from its CPU budget.
static uint32_t AudioWorkClock() {
  const uint32_t mask = __get_PRIMASK(); __disable_irq();
  const uint32_t tick = System::GetTick() - uint32_t(acquisition_work_ticks);
  __set_PRIMASK(mask); return tick;
}
#define EP_AUDIO_WORK_CLOCK() AudioWorkClock()
#define EP_AUDIO_MARKER(value) do { \
  if (!clock_diagnostic) audio_marker.Write(value); \
  else if (clock_output_active) diagnostic_audio_marker.Write(value); \
} while (0)
#include "dsp_workload.h"
extern "C" {
alignas(32) __attribute__((section(".ep_dsp_delay"), used))
int16_t ep_dsp_delay[dspbench::kVoices * dspbench::kDelay];
}
static dspbench::Engine dsp;
static uint32_t dsp_voices;
static void RenderDsp(float** out, size_t size, bool measure) {
  for (size_t i = 0; i < size; ++i) {
    if (measure && dsp_voices) { int16_t l, r; dsp.Frame(l, r); }
    out[0][i] = out[1][i] = 0.0f;
  }
}
#define EP_AUDIO_RENDER(out, size, measure) RenderDsp(out, size, measure)
#include "audio_load.h"
#include "dma_workload.h"
static ADC_HandleTypeDef adc;
extern "C" {
alignas(32) __attribute__((section(".ep_jack_records"), used))
jackbench::Record ep_jack_records[jackbench::kMaxRecords];
}
static auto& records = ep_jack_records;
static_assert(sizeof(records) <= 32 * 1024 * 1024, "Bound jack trace memory");
static_assert(ATOMIC_INT_LOCK_FREE == 2 && ATOMIC_BOOL_LOCK_FREE == 2, "USB IRQ mailbox");
static std::atomic<uint32_t> head{0}, tail{0};
static std::atomic<bool> busy{false}, abort_run{false}, overflow{false};
static std::atomic<bool> finish_requested{false};
static jackbench::FinishCommand finish_command;
static char rx[256];
static bool ready;
static void Receive(uint8_t* data, uint32_t* size) {
  for (uint32_t i = 0; i < *size; ++i) {
    if (busy.load(std::memory_order_acquire)) {
      const auto result = finish_command.Feed(static_cast<char>(data[i]));
      if (result == jackbench::FinishCommand::Result::kComplete)
        finish_requested.store(true, std::memory_order_release);
      if (result == jackbench::FinishCommand::Result::kInvalid)
        abort_run.store(true, std::memory_order_release);
      continue;
    }
    const uint32_t h = head.load(std::memory_order_relaxed);
    if (h - tail.load(std::memory_order_acquire) == sizeof(rx)) overflow.store(true);
    else { rx[h % sizeof(rx)] = static_cast<char>(data[i]); head.store(h + 1, std::memory_order_release); }
  }
}
static bool Read(char& c) {
  const uint32_t t = tail.load(std::memory_order_relaxed);
  if (t == head.load(std::memory_order_acquire)) return false;
  c = rx[t % sizeof(rx)]; tail.store(t + 1, std::memory_order_release); return true;
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
  // Single conversion with an explicit EOC interrupt establishes freshness.
  // Do not use AdcHandle's background DMA/cache as a freshness indicator.
  __HAL_RCC_ADC12_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  GPIO_InitTypeDef pin{};
  pin.Pin = GPIO_PIN_3; pin.Mode = GPIO_MODE_ANALOG; pin.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOA, &pin);
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
  ch.Channel = ADC_CHANNEL_15; // PA3 / D16 / A1 / physical pin 23.
  ch.Rank = ADC_REGULAR_RANK_1;
  ch.SamplingTime = ADC_SAMPLETIME_810CYCLES_5; // Long aperture for the 100k pull-down fixture.
  ch.SingleDiff = ADC_SINGLE_ENDED;
  ch.OffsetNumber = ADC_OFFSET_NONE;
  if (HAL_ADC_ConfigChannel(&adc, &ch) != HAL_OK) return false;
  // Prime/enable in foreground. Runtime start is a register write, with no HAL
  // timeout loop in a high-priority interrupt. Keep ADC enabled between samples.
  if (HAL_ADC_Start(&adc) != HAL_OK || HAL_ADC_PollForConversion(&adc, 2) != HAL_OK) return false;
  (void)HAL_ADC_GetValue(&adc);
  adc.Instance->ISR = ADC_ISR_EOC | ADC_ISR_EOS | ADC_ISR_OVR;
  adc.Instance->IER = 0;
  HAL_NVIC_SetPriority(ADC_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(ADC_IRQn);
  const uint32_t hz = System::GetPClk1Freq() * 2;
  if (hz % 1000000 || hz / 1000000 > 65536) return false;
  __HAL_RCC_TIM7_CLK_ENABLE();
  TIM7->CR1 = 0; TIM7->PSC = hz / 1000000 - 1; TIM7->ARR = 49;
  TIM7->EGR = TIM_EGR_UG; TIM7->SR = 0; TIM7->DIER = TIM_DIER_UIE;
  HAL_NVIC_SetPriority(TIM7_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(TIM7_IRQn);
  return true;
}
// Timer and ADC priority 0 serialize their state; SAI DMA priority 1 can be
// preempted. Only these handlers own acquisition state while running. The
// foreground reads it after TIM7 and ADC interrupts have been disabled.
struct AcquisitionRun {
  explicit AcquisitionRun(const jackbench::Plan& p) : acquisition(p), clock(System::GetTick(), System::GetTickFreq()) {}
  jackbench::Acquisition acquisition;
  bench::Clock clock;
  std::atomic<uint32_t> limit{0}, status{0};
  std::atomic<bool> done{false};
  uint32_t timer_irqs = 0, adc_irqs = 0, max_timer_ticks = 0, max_adc_ticks = 0;
  uint32_t timeouts = 0, overruns = 0, unexpected_irqs = 0;
};
static AcquisitionRun* active;
static uint32_t Now() { // Safe from foreground as well as either serialized ISR.
  const uint32_t mask = __get_PRIMASK(); __disable_irq();
  const uint32_t us = active->clock.Us(System::GetTick());
  __set_PRIMASK(mask); return us;
}
static void CompleteAdc(bool valid, uint16_t raw) {
  auto& a = active->acquisition;
  a.Converted(raw, valid, Now());
  presence_marker.Write(a.record.ready && a.record.patched);
  const uint32_t end = Now(); sample_marker.Write(false);
  a.Finished(end); records[a.count - 1] = a.record;
}
extern "C" void ADC_IRQHandler() {
  const uint32_t tick = System::GetTick();
  const uint32_t flags = adc.Instance->ISR;
  adc.Instance->IER = 0;
  const uint16_t raw = static_cast<uint16_t>(adc.Instance->DR);
  adc.Instance->ISR = ADC_ISR_EOC | ADC_ISR_EOS | ADC_ISR_OVR;
  if (!active || active->done.load()) return;
  ++active->adc_irqs;
  const bool valid = (flags & ADC_ISR_EOC) && !(flags & ADC_ISR_OVR);
  active->overruns += bool(flags & ADC_ISR_OVR);
  if (!(flags & ADC_ISR_EOC)) ++active->unexpected_irqs;
  CompleteAdc(valid, raw);
  if (!valid) active->status.store(4);
  const uint32_t work = System::GetTick() - tick;
  active->max_adc_ticks = std::max(active->max_adc_ticks, work);
  acquisition_work_ticks += work;
}
extern "C" void TIM7_IRQHandler() {
  const uint32_t tick = System::GetTick();
  TIM7->SR = 0;
  if (!active) return;
  ++active->timer_irqs;
  auto& a = active->acquisition;
  using Action = jackbench::Acquisition::Action;
  switch (a.Next(Now(), active->limit.load(std::memory_order_relaxed))) {
    case Action::kDrive:
      if (a.count == jackbench::kMaxRecords) { active->status.store(3); break; }
      probe_pin.Write(a.record.probe);
      // Settle from the physical write, not the preceding state-machine work.
      a.record.drive_us = Now();
      if (a.record.slot != a.record.drive_us / jackbench::kPeriodUs) active->status.store(4);
      break;
    case Action::kSample:
      sample_marker.Write(true);
      if (adc.Instance->CR & ADC_CR_ADSTART) {
        ++active->overruns; CompleteAdc(false, 0); active->status.store(4); break;
      }
      adc.Instance->ISR = ADC_ISR_EOC | ADC_ISR_EOS | ADC_ISR_OVR;
      adc.Instance->IER = ADC_IER_EOCIE | ADC_IER_OVRIE;
      adc.Instance->CR |= ADC_CR_ADSTART; break;
    case Action::kTimeout:
      // Fail closed; never wait for a peripheral with SysTick masked by priority.
      adc.Instance->IER = 0; ++active->timeouts;
      CompleteAdc(false, 0); active->status.store(4); break;
    case Action::kFinished: active->done.store(true); TIM7->CR1 = 0; break;
    case Action::kNone: break;
  }
  if (active->status.load()) { TIM7->CR1 = 0; active->done.store(true); }
  const uint32_t work = System::GetTick() - tick;
  active->max_timer_ticks = std::max(active->max_timer_ticks, work);
  acquisition_work_ticks += work;
}
static void Identity(char mode = 'J') {
  char text[512];
  std::snprintf(text, sizeof(text),
    "JINFO,{\"kind\":\"%s\",\"protocol\":9,\"board\":\"seed3\",\"build_id\":\"%s\","
    "\"ready\":%s,\"period_us\":500,\"settle_us\":150,\"window_size\":64,\"mismatch_threshold\":3,"
    "\"bad_windows_required\":8,\"low_code\":16384,\"high_code\":49151,\"max_records\":600000,"
    "\"timer_hz\":%u,\"adc_hz\":%u,\"sample_cycles_x2\":1621}\n",
    mode == 'M' ? "daisy-jack-clock-reference" :
      mode == 'K' ? "daisy-jack-clock-diagnostic" : "daisy-jack-bench",
    EP_BUILD_ID, ready ? "true" : "false", unsigned(System::GetTickFreq()), unsigned(AdcHz()));
  Send(text);
}
static void Run(const jackbench::Plan& plan, char mode = 'J') {
  const bool diagnostic = mode != 'J';
  clock_diagnostic = diagnostic;
  dsp_voices = plan.dsp_voices; dsp.Reset(dsp_voices, ep_dsp_delay);
  if (!dmabench::Reset(plan.dma_kib, plan.dma_region, plan.dma_period_us)) { Send("JERROR,dma_init\n"); return; }
  if (plan.audio_block && !audio_load::Start(plan.audio_block, plan.audio_permille)) {
    audio_load::Stop(); dmabench::Stop(); Send("JERROR,audio_init\n"); return;
  }
  const uint32_t guard = __get_PRIMASK(); __disable_irq();
  finish_command.Reset(plan.token); finish_requested.store(false);
  abort_run.store(false); busy.store(true);
  const bool pending = head.load() != tail.load() || overflow.load();
  tail.store(head.load()); __set_PRIMASK(guard);
  uint32_t status = pending ? 1 : 0;
  uint32_t limit_us = plan.duration_ms * 1000, request_us = 0, finish_reason = 0;
  char text[384];
  std::snprintf(text, sizeof(text), "%cSTART,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u\n", mode, unsigned(plan.token),
    unsigned(plan.duration_ms), unsigned(plan.fault), unsigned(plan.policy),
    unsigned(plan.trigger), unsigned(plan.delay_slots), unsigned(plan.fault_us),
    unsigned(plan.audio_block), unsigned(plan.audio_permille), unsigned(plan.audio_off_ms),
    unsigned(plan.dsp_voices), unsigned(plan.dma_kib),
    unsigned(plan.dma_region), unsigned(plan.dma_period_us));
  if (!status && !Send(text)) status = 2;
  sample_marker.Write(false); presence_marker.Write(false); probe_pin.Write(false);
  AcquisitionRun run(plan);
  auto& acquisition = run.acquisition;
  if (diagnostic && !status) ClockOutput(true);
  const uint32_t audio_guard = __get_PRIMASK(); __disable_irq();
  active = &run; run.limit.store(limit_us);
  acquisition_work_ticks = 0; audio_load::counters = {};
  // libDaisy initializes SAI1 DMA streams at priority 0; override explicitly.
  HAL_NVIC_SetPriority(DMA1_Stream0_IRQn, 1, 0);
  HAL_NVIC_SetPriority(DMA1_Stream1_IRQn, 1, 0);
  run.clock = bench::Clock(System::GetTick(), System::GetTickFreq());
  audio_load::measuring.store(plan.audio_block != 0, std::memory_order_relaxed);
  TIM7->CNT = 0; TIM7->SR = 0; NVIC_ClearPendingIRQ(TIM7_IRQn);
  if (!status) TIM7->CR1 = TIM_CR1_CEN;
  __set_PRIMASK(audio_guard);
  bool audio_running = plan.audio_block != 0;
  uint32_t audio_end_us = 0;
  auto stop_audio = [&]() {
    if (!audio_running) return;
    const uint32_t mask = __get_PRIMASK(); __disable_irq();
    audio_load::measuring.store(false, std::memory_order_relaxed);
    audio_end_us = Now();
    __set_PRIMASK(mask);
    audio_load::Stop(); audio_running = false;
  };
  while (!status && !run.done.load(std::memory_order_acquire)) {
    uint32_t us = Now();
    if (audio_running && us >= plan.audio_off_ms * 1000) stop_audio();
    if (!dmabench::Service(us, audio_running && !finish_requested.load() && us < run.limit.load())) {
      status = 5; break;
    }
    if (abort_run.load() || hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED) { status = 1; break; }
    if (!finish_reason && finish_requested.load(std::memory_order_acquire)) {
      const uint32_t mask = __get_PRIMASK(); __disable_irq();
      us = Now();
      if (us < plan.duration_ms * 1000 && !run.done.load()) {
        request_us = us; finish_reason = 1;
        limit_us = jackbench::ScheduledFinishLimit(plan, us);
        run.limit.store(limit_us, std::memory_order_release);
      }
      __set_PRIMASK(mask);
    }
  }
  const uint32_t release_guard = __get_PRIMASK(); __disable_irq();
  TIM7->CR1 = 0; adc.Instance->IER = 0;
  NVIC_ClearPendingIRQ(TIM7_IRQn); NVIC_ClearPendingIRQ(ADC_IRQn);
  sample_marker.Write(false); probe_pin.Write(false);
  const uint32_t elapsed = Now();
  if (!status) status = run.status.load();
  __set_PRIMASK(release_guard);
  stop_audio();
  while (!status && dmabench::pending)
    if (!dmabench::Service(Now(), false)) status = 5;
  dmabench::Stop(); active = nullptr;
  if (diagnostic) ClockOutput(false);
  // An aborted/hung conversion is recovered only in foreground. No partial run
  // can pass the host's status/hash/timing checks.
  if (status) { HAL_ADC_Stop(&adc); ready = false; }
  const uint32_t count = acquisition.count, missed = acquisition.missed, failures = acquisition.failures;
  const uint32_t fault_begin = acquisition.fault_begin, fault_end = acquisition.fault_end;
  const auto& fault = acquisition.fault();
  uint32_t hash = 2166136261u;
  std::snprintf(text, sizeof(text), "JFINISH,%u,%u,%u,%u\n", unsigned(plan.token),
    unsigned(request_us), unsigned(limit_us), unsigned(finish_reason));
  bool sent = Send(text);
  hash = bench::Hash(hash, text, std::strlen(text));
  std::snprintf(text, sizeof(text), "JTIMING,%u,%u,%u,%u,%u,%u\n",
    unsigned(plan.trigger), unsigned(plan.delay_slots), unsigned(plan.fault_us),
    unsigned(fault.event_seq()), unsigned(fault.event_us()), unsigned(fault.due_us()));
  sent = sent && Send(text); hash = bench::Hash(hash, text, std::strlen(text));
  const auto& ac = audio_load::counters;
  std::snprintf(text, sizeof(text), "JLOAD,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u\n",
    unsigned(plan.audio_block), unsigned(plan.audio_permille), unsigned(plan.audio_off_ms),
    unsigned(audio_end_us), unsigned(ac.callbacks), unsigned(ac.max_work_ticks),
    unsigned(ac.max_interval_ticks), unsigned(ac.over_budget), unsigned(ac.late_intervals),
    unsigned(ac.bad_size), plan.audio_block ? unsigned(audio_load::period_ticks) : 0u,
    unsigned(System::GetTickFreq()));
  sent = sent && Send(text); hash = bench::Hash(hash, text, std::strlen(text));
  std::snprintf(text, sizeof(text), "JACQ,50,0,0,1,%u,%u,%u,%u,%u,%u,%u,%u,%u,1\n",
    unsigned(run.timer_irqs), unsigned(run.adc_irqs), unsigned(run.max_timer_ticks), unsigned(run.max_adc_ticks),
    unsigned(uint32_t(acquisition_work_ticks)), unsigned(acquisition_work_ticks >> 32),
    unsigned(run.timeouts), unsigned(run.overruns), unsigned(run.unexpected_irqs));
  sent = sent && Send(text); hash = bench::Hash(hash, text, std::strlen(text));
  const auto& ds = dsp.signature();
  std::snprintf(text, sizeof(text), "JDSP,%u,%u,%u,%u,%u,%u\n",
    unsigned(plan.dsp_voices), unsigned(ds.frames), unsigned(ds.hash), unsigned(ds.peak),
    unsigned(ds.nonzero), unsigned(ds.macs));
  sent = sent && Send(text); hash = bench::Hash(hash, text, std::strlen(text));
  const auto& dc = dmabench::counters;
  std::snprintf(text, sizeof(text), "JDMA,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u,%u\n",
    unsigned(plan.dma_kib), plan.dma_kib ? unsigned(plan.dma_period_us) : 0u,
    unsigned(dc.started), unsigned(dc.completed), unsigned(dc.verified), unsigned(dc.bytes),
    unsigned(dc.errors), unsigned(dc.corrupt_words), unsigned(dc.timeouts), unsigned(dc.skipped),
    unsigned(dc.first_us), unsigned(dc.last_us), unsigned(dc.max_gap_us), unsigned(dc.max_transfer_ticks),
    unsigned(dmabench::irq_count), unsigned(dmabench::max_irq_ticks), plan.dma_kib ? 2u : 0u,
    plan.dma_kib ? 6u : 0u);
  sent = sent && Send(text); hash = bench::Hash(hash, text, std::strlen(text));
  std::snprintf(text, sizeof(text), "JMEM,%u,%u,%u,%u,%u\n",
    plan.dma_kib ? unsigned(plan.dma_region) : 0u,
    unsigned(uint32_t(dmabench::source)), unsigned(uint32_t(dmabench::destination)),
    plan.dma_kib ? unsigned(dmaconfig::kBufferBytes) : 0u,
    plan.dma_kib ? unsigned(dmaconfig::kCacheLineBytes) : 0u);
  sent = sent && Send(text); hash = bench::Hash(hash, text, std::strlen(text));
  std::snprintf(text, sizeof(text), "JFAULT,%u,%u\n", unsigned(fault_begin), unsigned(fault_end));
  sent = sent && Send(text);
  hash = bench::Hash(hash, text, std::strlen(text));
  std::snprintf(text, sizeof(text), "JCOLUMNS,%s\n", jackbench::kColumns);
  sent = sent && Send(text); hash = bench::Hash(hash, text, std::strlen(text));
  for (uint32_t i = 0; i < count && sent; ++i) {
    const int n = jackbench::Format(text, sizeof(text), records[i]);
    sent = n > 0 && static_cast<size_t>(n) < sizeof(text) && Send(text);
    if (sent) hash = bench::Hash(hash, text, static_cast<size_t>(n));
  }
  // Duplicate token-bound finishes are harmless, including a deadline race.
  // Unknown traffic and partial commands still invalidate the entire run.
  const uint32_t finish_guard = __get_PRIMASK(); __disable_irq();
  if ((abort_run.load() || finish_command.Incomplete()) && !status) status = 1;
  __set_PRIMASK(finish_guard);
  if (sent) {
    std::snprintf(text, sizeof(text), "JEND,%u,%u,%u,%u,%u,%u,%u\n", unsigned(plan.token),
      unsigned(count), unsigned(status), unsigned(missed), unsigned(failures), unsigned(elapsed), unsigned(hash));
    Send(text);
  }
  busy.store(false, std::memory_order_release);
}
int main() {
  const bool old_boot = System::GetBootloaderVersion() == System::BootInfo::Version::LT_v6_0;
  System::Config cfg; cfg.Boost(); cfg.skip_clocks = old_boot; system_hw.Init(cfg);
  ready = old_boot || memory.Init() == SdramHandle::Result::OK;
  probe_pin.Init(Pin(PORTC, 10), GPIO::Mode::INPUT); probe_pin.Write(false);
  probe_pin.Init(Pin(PORTC, 10), GPIO::Mode::OUTPUT, GPIO::Pull::NOPULL);
  sample_marker.Init(Pin(PORTB, 12), GPIO::Mode::OUTPUT);
  presence_marker.Init(Pin(PORTC, 11), GPIO::Mode::OUTPUT);
  audio_marker.Init(Pin(PORTC, 9), GPIO::Mode::OUTPUT); // D3 / physical pin 4.
  audio_marker.Write(false);
  diagnostic_audio_marker.Init(Pin(PORTC, 8), GPIO::Mode::OUTPUT);
  diagnostic_audio_marker.Write(false); // Stable pre/post-roll, including J mode.
  sample_marker.Write(false); presence_marker.Write(false);
  ready = ready && InitAdc();
  usb.Init(UsbHandle::FS_INTERNAL); usb.SetReceiveCallback(Receive, UsbHandle::FS_INTERNAL);
  char command[96]; size_t used = 0; bool bad = false;
  while (true) {
    if (overflow.exchange(false)) bad = true;
    char c; if (!Read(c)) continue;
    if (c == '\r') continue;
    if (c != '\n') {
      if (c < 32 || c > 126 || used + 1 >= sizeof(command)) bad = true;
      else command[used++] = c;
      continue;
    }
    command[used] = '\0'; jackbench::Plan plan;
    if (bad) Send("JERROR,command_length\n");
    else if (std::strcmp(command, "?") == 0) Identity();
    else if (std::strcmp(command, "K?") == 0) Identity('K');
    else if (std::strcmp(command, "M?") == 0) Identity('M');
    else {
      const char mode = command[0];
      if (mode == 'K' || mode == 'M') command[0] = 'J';
      if (ready && jackbench::Parse(command, plan) &&
          (mode != 'K' || jackbench::ValidClockDiagnosticPlan(plan)) &&
          (mode != 'M' || jackbench::ValidClockReferencePlan(plan)))
        Run(plan, mode);
      else Send("JERROR,command_or_not_ready\n");
    }
    used = 0; bad = false;
  }
}
