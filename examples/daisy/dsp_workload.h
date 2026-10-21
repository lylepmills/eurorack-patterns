// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EP_DAISY_DSP_WORKLOAD_H_
#define EP_DAISY_DSP_WORKLOAD_H_
#include <algorithm>
#include <cstddef>
#include <cstdint>

// Deterministic fixed-point signal processing for a measurement fixture. This
// is a real 32-tap triangular FIR and feedback delay, not a calibrated CPU load
// or a production audio engine. Integer division truncates toward zero on all
// targets; all signed intermediates fit int32_t. Caller owns delay storage.
namespace dspbench {
constexpr uint32_t kVoices = 32, kTaps = 32, kDelay = 32768;
constexpr uint32_t kInitialHash = 2166136261u;
inline uint32_t Word(uint32_t epoch, uint32_t index) {
  return (epoch * 0x9e3779b9u) ^ (index * 0x85ebca6bu) ^ 0xa5c36917u;
}
class Fir {
 public:
  int32_t Process(int16_t x) {
    history_[head_] = x;
    int32_t sum = 0;
    for (uint32_t i = 0; i < kTaps; ++i) {
      const int32_t coefficient = static_cast<int32_t>(i < 16 ? i + 1 : 32 - i);
      sum += int32_t(history_[(head_ - i) & 31u]) * coefficient;
    }
    head_ = (head_ + 1) & 31u;
    return sum / 272;
  }
 private:
  int16_t history_[kTaps]{};
  uint32_t head_ = 0;
};
struct Signature {
  uint32_t frames = 0, hash = kInitialHash, peak = 0, nonzero = 0, macs = 0;
};
class Engine {
 public:
  // Reset accepts 0..kVoices and storage for voices*kDelay samples. A disabled
  // engine (voices=0) is resettable but must not receive Frame calls.
  void Reset(uint32_t voices, int16_t* delay) {
    voices_ = voices; delay_ = delay; signature_ = {}; position_ = 0;
    for (uint32_t v = 0; v < voices; ++v) {
      filters_[v] = Fir{}; random_[v] = 0x12345678u ^ ((v + 1) * 0x9e3779b9u);
    }
    if (voices) std::fill(delay, delay + voices * kDelay, int16_t(0));
  }
  void Frame(int16_t& left, int16_t& right) {
    int32_t sums[2]{};
    for (uint32_t v = 0; v < voices_; ++v) {
      uint32_t x = random_[v]; x ^= x << 13; x ^= x >> 17; x ^= x << 5; random_[v] = x;
      const int16_t input = static_cast<int16_t>(int32_t(x & 16383u) - 8192);
      const int32_t dry = filters_[v].Process(input);
      const uint32_t base = v * kDelay, distance = 1024 + v * 997;
      const int32_t wet = delay_[base + ((position_ - distance) & (kDelay - 1))];
      const int32_t feedback = dry + wet / 4;
      delay_[base + position_] = static_cast<int16_t>(feedback);
      sums[v & 1u] += (dry + wet) / 2;
    }
    position_ = (position_ + 1) & (kDelay - 1);
    left = static_cast<int16_t>(sums[0] / int32_t((voices_ + 1) / 2));
    right = static_cast<int16_t>(sums[1] / int32_t(std::max<uint32_t>(voices_ / 2, 1)));
    ++signature_.frames; signature_.macs += voices_ * kTaps;
    signature_.nonzero += left != 0 || right != 0;
    for (int16_t sample : {left, right}) {
      const int32_t value = sample;
      signature_.peak = std::max(signature_.peak, uint32_t(value < 0 ? -value : value));
      const uint16_t bits = static_cast<uint16_t>(sample);
      signature_.hash = (signature_.hash ^ (bits & 255u)) * 16777619u;
      signature_.hash = (signature_.hash ^ (bits >> 8)) * 16777619u;
    }
  }
  const Signature& signature() const { return signature_; }
 private:
  Fir filters_[kVoices];
  uint32_t random_[kVoices]{}, voices_ = 0, position_ = 0;
  int16_t* delay_ = nullptr;
  Signature signature_;
};
} // namespace dspbench
#endif
