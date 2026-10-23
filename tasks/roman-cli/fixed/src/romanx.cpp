// A reference implementation of the roman-cli task -- the answer key.
//
// It exists for one reason: to prove the acceptance corpus can pass. An oracle that only
// ever fails is not evidence of anything, so this is the positive control that `ninny
// verify-task` runs the corpus against.
#include "romanx/romanx.hpp"

#include <array>
#include <string>
#include <utility>

namespace romanx {
namespace {

// Largest first, with the subtractive pairs in the sequence: greedy consumption then
// produces the canonical form, and nothing else.
constexpr std::array<std::pair<long long, std::string_view>, 13> VALUES{{
    {1000, "M"}, {900, "CM"}, {500, "D"}, {400, "CD"}, {100, "C"}, {90, "XC"},
    {50, "L"},   {40, "XL"},  {10, "X"},  {9, "IX"},   {5, "V"},   {4, "IV"},
    {1, "I"},
}};

constexpr long long digit_value(char c) {
  switch (c) {
    case 'I': return 1;
    case 'V': return 5;
    case 'X': return 10;
    case 'L': return 50;
    case 'C': return 100;
    case 'D': return 500;
    case 'M': return 1000;
    default: return -1;
  }
}

}  // namespace

std::optional<std::string> to_roman(long long n) {
  if (n < 1 || n > 3999) return std::nullopt;
  std::string out;
  for (const std::pair<long long, std::string_view>& pair : VALUES) {
    while (n >= pair.first) {
      out.append(pair.second);
      n -= pair.first;
    }
  }
  return out;
}

std::optional<long long> to_number(std::string_view s) {
  if (s.empty()) return std::nullopt;
  long long total = 0;
  long long previous = 0;
  for (std::string_view::const_reverse_iterator it = s.rbegin(); it != s.rend(); ++it) {
    const long long value = digit_value(*it);
    if (value < 0) return std::nullopt;
    if (value < previous) {
      total -= value;
    } else {
      total += value;
      previous = value;
    }
  }
  // Accept exactly the canonical form of its own value: this is the whole rule.
  const std::optional<std::string> canonical = to_roman(total);
  if (!canonical || *canonical != s) return std::nullopt;
  return total;
}

}  // namespace romanx
