// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#ifndef EURORACK_PATTERNS_GESTURES_H_
#define EURORACK_PATTERNS_GESTURES_H_

namespace eurorack_patterns {

// One physical button's role is chosen at press time, not at release time.
// Role is usually an enum class owned by the UI. A consumed/cancelled press
// stays latched until release, so navigation cannot create another action.
// Call from one event owner/thread; this class does no synchronization.
template <typename Role>
class RoleLatch {
 public:
  RoleLatch() : pressed_(false), consumed_(false), role_() {}

  bool Press(Role role) {
    if (pressed_) return false;
    role_ = role;
    pressed_ = true;
    consumed_ = false;
    return true;
  }

  // A combined gesture takes ownership of the pending release. Run any
  // necessary role-end action (such as EndShift) at the point of consumption.
  bool Consume() {
    if (!pressed_ || consumed_) return false;
    consumed_ = true;
    return true;
  }

  // A navigation/reset cancellation has the same release-suppression contract.
  bool Cancel() { return Consume(); }

  // Returns true only for an unconsumed press. On false, out is untouched.
  // Every actual release clears the latch, including a consumed one.
  bool Release(Role& out) {
    if (!pressed_) return false;
    const bool actionable = !consumed_;
    if (actionable) out = role_;
    pressed_ = false;
    consumed_ = false;
    return actionable;
  }

  bool CurrentRole(Role& out) const {
    if (!pressed_) return false;
    out = role_;
    return true;
  }
  bool IsPressed() const { return pressed_; }
  bool IsConsumed() const { return pressed_ && consumed_; }

 private:
  bool pressed_;
  bool consumed_;
  Role role_;
};

}  // namespace eurorack_patterns
#endif  // EURORACK_PATTERNS_GESTURES_H_
