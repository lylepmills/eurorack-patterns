// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "sys/system.h"
#include "hid/usb.h"
#include "per/gpio.h"
#include "stm32h7xx_hal.h"
#include "usbd_cdc.h"
#include "build_identity.h"
#include "pulse_generator.h"
#include "bench.h"
#include <atomic>
#include <cstdio>
#include <cstring>

using namespace daisy;
extern "C" USBD_HandleTypeDef hUsbDeviceFS;
static System system_hw;
static UsbHandle usb;
static GPIO output;
static std::atomic<uint32_t> head{0}, tail{0};
static std::atomic<bool> running{false}, abort_run{false}, overflow{false};
static_assert(ATOMIC_INT_LOCK_FREE == 2 && ATOMIC_BOOL_LOCK_FREE == 2,
              "USB mailbox requires lock-free atomics");
static char rx[2048];
static bool armed = false;
static uint32_t armed_ms = 0;
static pulsegen::Plan plan;

static void Receive(uint8_t* data, uint32_t* size) {
  for (uint32_t i = 0; i < *size; ++i) {
    if (running.load(std::memory_order_acquire)) {
      // X is the documented abort; unexpected traffic also cancels a run.
      // Do not leave commands queued to execute after a timed sequence.
      abort_run.store(true, std::memory_order_release);
      continue;
    }
    const uint32_t h = head.load(std::memory_order_relaxed);
    if (h - tail.load(std::memory_order_acquire) == sizeof(rx)) {
      overflow.store(true, std::memory_order_release);
    } else {
      rx[h % sizeof(rx)] = static_cast<char>(data[i]);
      head.store(h + 1, std::memory_order_release);
    }
  }
}
static bool Read(char& c) {
  const uint32_t t = tail.load(std::memory_order_relaxed);
  if (t == head.load(std::memory_order_acquire)) return false;
  c = rx[t % sizeof(rx)]; tail.store(t + 1, std::memory_order_release);
  return true;
}
static bool TxIdle() {
  const uint32_t mask = __get_PRIMASK(); __disable_irq();
  volatile USBD_HandleTypeDef* device = &hUsbDeviceFS;
  const auto* cdc = static_cast<USBD_CDC_HandleTypeDef*>(device->pClassData);
  const bool idle = device->dev_state == USBD_STATE_CONFIGURED && cdc && !cdc->TxState;
  __set_PRIMASK(mask);
  return idle;
}
static bool Send(const char* text) {
  static uint8_t tx[512]; // Retain storage until transfer actually completes.
  const size_t n = std::strlen(text);
  if (n > sizeof(tx)) return false;
  uint32_t start = System::GetNow();
  while (true) {
    bool queued = false;
    const uint32_t mask = __get_PRIMASK(); __disable_irq();
    if (TxIdle()) {
      std::memcpy(tx, text, n);
      queued = usb.TransmitInternal(tx, n) == UsbHandle::Result::OK;
    }
    __set_PRIMASK(mask);
    if (queued) break;
    if (uint32_t(System::GetNow() - start) > 2000) return false;
  }
  start = System::GetNow();
  while (!TxIdle()) if (uint32_t(System::GetNow() - start) > 2000) return false;
  return true;
}
static void Release() { output.Write(true); armed = false; }
static void Identity() {
  char line[384];
  std::snprintf(line, sizeof(line),
    "GENINFO,{\"protocol\":1,\"kind\":\"daisy-pulse-generator\",\"board\":\"seed3\","
    "\"build_id\":\"%s\",\"timer_hz\":%u,\"armed\":%s,\"released\":true,"
    "\"max_edges\":64,\"max_us\":30000000,\"max_late_us\":25}\n",
    EP_BUILD_ID, unsigned(System::GetTickFreq()), armed ? "true" : "false");
  Send(line); // released describes commanded high-impedance, not line voltage.
}
static void Run() {
  struct Edge { uint32_t before, after; } edges[pulsegen::kMaxEdges]{};
  const uint32_t mask = __get_PRIMASK(); __disable_irq();
  abort_run.store(false); running.store(true);
  // A pipelined command cannot become a second, unobserved run.
  const bool pending = head.load() != tail.load() || overflow.load();
  tail.store(head.load());
  __set_PRIMASK(mask);
  Release(); // Consume the plan's arm before any blocking USB operation.
  char line[128];
  std::snprintf(line, sizeof(line), "GENSTART,%u,%u\n", unsigned(plan.token), unsigned(plan.count));
  uint32_t status = pending ? 1 : 0;
  if (!status && !Send(line)) status = 2;
  pulsegen::Sequence sequence(plan);
  bench::Clock clock(System::GetTick(), System::GetTickFreq());
  bool pressed = false;
  while (!status && sequence.count() < plan.count) {
    volatile USBD_HandleTypeDef* device = &hUsbDeviceFS;
    if (abort_run.load() || device->dev_state != USBD_STATE_CONFIGURED) { status = 1; break; }
    const uint32_t guard = __get_PRIMASK(); __disable_irq();
    const uint32_t before = clock.Us(System::GetTick());
    const auto result = sequence.Poll(before, pressed);
    if (result == pulsegen::Sequence::kEdge) {
      output.Write(!pressed); // Low = press; high-impedance = release. Never drive high.
      const uint32_t after = clock.Us(System::GetTick());
      const uint32_t i = sequence.count() - 1;
      edges[i] = {before, after};
      if (after - plan.times[i] > pulsegen::kMaxLateUs) status = 3;
    } else if (result == pulsegen::Sequence::kLate) status = 3;
    __set_PRIMASK(guard);
  }
  Release();
  const uint32_t end_us = clock.Us(System::GetTick());
  // Still reject incoming traffic while formatting; output is already released.
  for (uint32_t i = 0; i < sequence.count(); ++i) {
    std::snprintf(line, sizeof(line), "GENEDGE,%u,%u,%u,%u,%u\n", unsigned(i),
      unsigned(plan.times[i]), unsigned(edges[i].before), unsigned(edges[i].after), unsigned(i % 2 == 0));
    if (!Send(line)) { status = 2; break; }
  }
  std::snprintf(line, sizeof(line), "GENEND,%u,%u,%u,%u\n", unsigned(plan.token),
    unsigned(sequence.count()), unsigned(status), unsigned(end_us));
  running.store(false, std::memory_order_release);
  Send(line);
}
int main() {
  const bool old_boot = System::GetBootloaderVersion() == System::BootInfo::Version::LT_v6_0;
  System::Config cfg; cfg.Boost(); cfg.skip_clocks = old_boot;
  system_hw.Init(cfg);
  // Preload ODR while still an input so changing mode cannot create a low pulse.
  output.Init(Pin(PORTB, 12), GPIO::Mode::INPUT);
  output.Write(true);
  output.Init(Pin(PORTB, 12), GPIO::Mode::OPEN_DRAIN, GPIO::Pull::NOPULL);
  Release();
  usb.Init(UsbHandle::FS_INTERNAL);
  usb.SetReceiveCallback(Receive, UsbHandle::FS_INTERNAL);
  char command[1024]; size_t used = 0; bool too_long = false;
  while (true) {
    if (armed && uint32_t(System::GetNow() - armed_ms) >= 30000) Release();
    if (overflow.exchange(false)) { Release(); too_long = true; }
    char c;
    if (!Read(c)) continue;
    if (c == '\r') continue;
    if (c != '\n') {
      if (c < 32 || c > 126) { too_long = true; continue; }
      if (used + 1 < sizeof(command)) command[used++] = c; else too_long = true;
      continue;
    }
    command[used] = '\0';
    uint32_t token = 0;
    if (too_long) { Release(); Send("GENERROR,command_length\n"); }
    else if (std::strcmp(command, "?") == 0) Identity();
    else if (std::strcmp(command, "X") == 0) { Release(); Send("GENABORT\n"); }
    else if (pulsegen::ParsePlan(command, plan)) {
      Release(); armed = true; armed_ms = System::GetNow();
      char line[96];
      std::snprintf(line, sizeof(line), "GENARMED,%u,%u,%u\n", unsigned(plan.token),
        unsigned(plan.count), unsigned(plan.times[plan.count-1]));
      if (!Send(line)) Release();
    } else if (pulsegen::ParseRun(command, token) && armed && token == plan.token) Run();
    else { Release(); Send("GENERROR,command_or_not_armed\n"); }
    used = 0; too_long = false;
  }
}
