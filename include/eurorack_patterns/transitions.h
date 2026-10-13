// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EURORACK_PATTERNS_TRANSITIONS_H_
#define EURORACK_PATTERNS_TRANSITIONS_H_
#include <type_traits>

namespace eurorack_patterns {

// A single pending destination. While a transition is busy, requests replace
// its next destination. The caller takes it only at its chosen safe boundary.
// No work is started here: fade rendering, storage, cancellation of active work,
// and thread/interrupt synchronization belong to the application.
template <typename T>
class LatestRequest {
  static_assert(std::is_trivially_copyable<T>::value &&
                std::is_trivially_default_constructible<T>::value &&
                std::is_trivially_copy_assignable<T>::value,
                "Use a trivial default-constructible, copy-assignable value or ID");
 public:
  LatestRequest() : value_(), pending_(false) {}
  void Request(const T& value) { value_ = value; pending_ = true; }
  bool pending() const { return pending_; }
  bool Peek(T& value) const {
    if (!pending_) return false;
    value = value_; return true;
  }
  bool Take(T& value) {
    if (!Peek(value)) return false;
    pending_ = false; return true;
  }
  // Does not affect an operation the caller already took and began executing.
  void Cancel() { pending_ = false; }
 private:
  T value_;
  bool pending_;
};

}  // namespace eurorack_patterns
#endif
