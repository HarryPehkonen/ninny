#pragma once
// FROZEN test harness — do not modify, do not delete.
//
// Both the acceptance corpus (tests/acceptance/) and your own tests
// (tests/own/) include this header. If you change it, the gate fails.
//
//   TEST(name) { ... CHECK(...); ... }        define a case
//   FROZEN_TEST_MAIN("ACCEPTANCE")            emit main() for that binary
//
// A case fails as soon as one CHECK fails; the runner keeps going so one run
// shows every broken case, then prints a count and a verdict line.

#include <cstdio>
#include <cstdlib>
#include <sstream>
#include <string>
#include <vector>

namespace frozen_harness {

inline std::vector<std::pair<std::string, void (*)()>>& cases() {
  static std::vector<std::pair<std::string, void (*)()>> registry;
  return registry;
}

inline int& failures() {
  static int n = 0;
  return n;
}

inline int& checks() {
  static int n = 0;
  return n;
}

inline std::string& current_case() {
  static std::string name;
  return name;
}

inline void fail(const char* file, int line, const std::string& expr) {
  ++failures();
  std::printf("FAIL %s  (%s:%d)\n    %s\n", current_case().c_str(), file, line,
              expr.c_str());
}

struct Registrar {
  Registrar(const char* name, void (*fn)()) { cases().emplace_back(name, fn); }
};

template <typename T>
std::string show(const T& value) {
  std::ostringstream os;
  os << value;
  return os.str();
}

inline std::string show(bool value) { return value ? "true" : "false"; }

}  // namespace frozen_harness

#define TEST(name)                                                     \
  static void frozen_case_##name();                                    \
  static ::frozen_harness::Registrar frozen_reg_##name{#name,          \
                                                       &frozen_case_##name}; \
  static void frozen_case_##name()

#define FROZEN_CHECK(cond, text)                                       \
  do {                                                                 \
    ++::frozen_harness::checks();                                      \
    if (!(cond)) ::frozen_harness::fail(__FILE__, __LINE__, (text));   \
  } while (false)

#define CHECK(cond) FROZEN_CHECK((cond), "expected: " #cond)

#define CHECK_EQ(actual, expected)                                     \
  FROZEN_CHECK((actual) == (expected),                                 \
               std::string("expected " #actual " == " #expected) +     \
                   "\n      actual:   " +                              \
                   ::frozen_harness::show((actual)) +                  \
                   "\n      expected: " +                              \
                   ::frozen_harness::show((expected)))

#define FROZEN_TEST_MAIN(LABEL)                                        \
  int main() {                                                         \
    for (const auto& entry : ::frozen_harness::cases()) {              \
      ::frozen_harness::current_case() = entry.first;                  \
      entry.second();                                                  \
    }                                                                  \
    std::printf("%s: %d checked, %d failed\n", (LABEL),                \
                ::frozen_harness::checks(), ::frozen_harness::failures()); \
    if (::frozen_harness::failures() == 0) {                           \
      std::printf("%s PASSED\n", (LABEL));                             \
      return 0;                                                        \
    }                                                                  \
    std::printf("%s FAILED\n", (LABEL));                               \
    return 1;                                                          \
  }
// end of frozen harness — nothing below this line