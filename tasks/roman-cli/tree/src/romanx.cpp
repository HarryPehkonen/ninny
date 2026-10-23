// Implement this file.
//
// The header beside it is frozen, the command line in main.cpp is frozen, and the test
// harness in ../tests/harness.hpp is frozen. Everything you write goes here.
//
// This file compiles as it stands -- it is a stub that compiles, not a build error --
// so your first own-test run will be a test that ran and failed, which is what a RED
// observation is supposed to be. Write the cases you would want to defend in
// tests/own/, watch them fail, then make them pass.
#include "romanx/romanx.hpp"

namespace romanx {

std::optional<std::string> to_roman(long long n) {
  (void)n;
  return std::nullopt;
}

std::optional<long long> to_number(std::string_view s) {
  (void)s;
  return std::nullopt;
}

}  // namespace romanx
