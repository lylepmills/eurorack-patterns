// SPDX-License-Identifier: MIT
// Copyright 2026 Lyle Mills
#include "eurorack_patterns/gestures.h"
#include <cstdio>
#include <cstdlib>

using namespace eurorack_patterns;
#define CHECK(condition) do { if (!(condition)) { \
  std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
  std::exit(1); } } while (0)

enum class ButtonRole { Shift, Back, Home, Cancel };

int main() {
  RoleLatch<ButtonRole> button;
  ButtonRole action = ButtonRole::Cancel;
  CHECK(!button.Release(action) && action == ButtonRole::Cancel);
  CHECK(!button.Consume());
  CHECK(button.Press(ButtonRole::Shift));
  CHECK(!button.Press(ButtonRole::Back));  // bounce cannot replace the role
  CHECK(button.IsPressed() && !button.IsConsumed());
  CHECK(button.CurrentRole(action) && action == ButtonRole::Shift);
  // Navigation changes the current page, but the pending release stays Shift.
  CHECK(button.Release(action) && action == ButtonRole::Shift);
  CHECK(!button.IsPressed());

  CHECK(button.Press(ButtonRole::Shift));
  CHECK(button.Consume());  // SHIFT + encoder tap runs EndShift now
  CHECK(!button.Consume());
  action = ButtonRole::Cancel;
  CHECK(!button.Release(action) && action == ButtonRole::Cancel);
  CHECK(button.Press(ButtonRole::Home));
  CHECK(button.Release(action) && action == ButtonRole::Home);

  CHECK(button.Press(ButtonRole::Back));
  CHECK(button.Cancel());  // leaving an editor cannot trigger another Back
  CHECK(button.IsConsumed());
  CHECK(!button.Release(action) && action == ButtonRole::Home);
  CHECK(button.Press(ButtonRole::Cancel));
  CHECK(button.Release(action) && action == ButtonRole::Cancel);
  CHECK(!button.CurrentRole(action));
  std::puts("PASS gestures");
}
