// The acceptance corpus for the roman-cli task.
//
// It lives OUTSIDE the task tree, and `ninny check` stages the submission beside this
// file rather than running inside it, so the agent never reads it. If it could, it could
// write its own tests from the answer key and both "did it write tests" and "did it write
// them first" would stop meaning anything.
//
// It carries its own copy of the frozen harness, so it does not depend on the tree's copy
// being intact -- accept.sh checks the hash of that too, in its own place.
#include <optional>
#include <string>
#include <vector>

#include "harness.hpp"
#include "romanx/romanx.hpp"

namespace {

struct Case {
  long long value;
  const char* text;
};

const std::vector<Case> VALID = {
    {1, "I"},       {2, "II"},      {3, "III"},          {4, "IV"},
    {5, "V"},       {6, "VI"},      {7, "VII"},          {8, "VIII"},
    {9, "IX"},      {10, "X"},      {11, "XI"},          {14, "XIV"},
    {19, "XIX"},    {40, "XL"},     {44, "XLIV"},        {49, "XLIX"},
    {50, "L"},      {90, "XC"},     {99, "XCIX"},        {100, "C"},
    {400, "CD"},    {444, "CDXLIV"}, {500, "D"},         {900, "CM"},
    {999, "CMXCIX"}, {1000, "M"},   {1987, "MCMLXXXVII"}, {2026, "MMXXVI"},
    {3888, "MMMDCCCLXXXVIII"},      {3999, "MMMCMXCIX"},
};

const std::vector<const char*> INVALID = {
    "",    "A",     "IIII", "VV",    "LL",   "DD",    "MMMM", "IVI",
    "XIIX", "ix",   "12",   "M M",   "CMCMC", "IC",   "IM",   "XXXX",
    "IIX",  " V",   "V ",   "\u2160",
};

const std::vector<long long> OUT_OF_RANGE = {0, -1, -3999, 4000, 5000, 1000000000LL};

std::string quoted(const std::string& s) { return "\"" + s + "\""; }

}  // namespace

TEST(to_roman_covers_the_whole_range) {
  for (const Case& c : VALID) {
    const std::optional<std::string> got = romanx::to_roman(c.value);
    FROZEN_CHECK(got.has_value() && *got == c.text,
                 std::string("to_roman(") + std::to_string(c.value) + ")" +
                     " expected " + c.text + " got " +
                     (got ? *got : std::string("<nothing>")));
  }
}

TEST(out_of_range_is_not_a_numeral) {
  for (const long long n : OUT_OF_RANGE) {
    const std::optional<std::string> got = romanx::to_roman(n);
    FROZEN_CHECK(!got.has_value(),
                 std::string("to_roman(") + std::to_string(n) +
                     ") should be nullopt and was not");
  }
}

TEST(what_the_tool_prints_is_what_it_accepts) {
  for (const Case& c : VALID) {
    const std::optional<long long> back = romanx::to_number(c.text);
    FROZEN_CHECK(back.has_value() && *back == c.value,
                 std::string("to_number(") + quoted(c.text) + ") expected " +
                     std::to_string(c.value) + " got " +
                     (back ? std::to_string(*back) : std::string("<nothing>")));
  }
}

TEST(non_canonical_input_is_rejected) {
  for (const char* s : INVALID) {
    const std::optional<long long> got = romanx::to_number(s);
    FROZEN_CHECK(!got.has_value(),
                 std::string("to_number(") + quoted(s) + ") accepted it as " +
                     (got ? std::to_string(*got) : std::string("<nothing>")));
  }
}

TEST(round_tripping_holds_for_every_value) {
  int broken = 0;
  std::string first;
  for (long long n = 1; n <= 3999; ++n) {
    const std::optional<std::string> text = romanx::to_roman(n);
    if (!text) {
      ++broken;
      if (first.empty()) first = "to_roman(" + std::to_string(n) + ") gave nothing";
      continue;
    }
    const std::optional<long long> back = romanx::to_number(*text);
    if (!back || *back != n) {
      ++broken;
      if (first.empty()) {
        first = "n=" + std::to_string(n) + " -> " + *text + " -> " +
                (back ? std::to_string(*back) : std::string("<nothing>"));
      }
    }
  }
  FROZEN_CHECK(broken == 0, "round trips broken: " + std::to_string(broken) +
                                (first.empty() ? std::string() : " first " + first));
}

FROZEN_TEST_MAIN("ACCEPTANCE")
