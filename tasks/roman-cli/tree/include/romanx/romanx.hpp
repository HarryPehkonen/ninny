#pragma once
// FROZEN CONTRACT -- do not modify. The acceptance corpus is compiled against this
// header, and the oracle checks its hash before it builds anything.
//
// Two functions, and both directions have to agree with each other:
//
//   to_roman(n)    the canonical Roman numeral for n, or std::nullopt when n is
//                  outside 1..3999
//   to_number(s)   the value of a CANONICAL Roman numeral, or std::nullopt when s is
//                  not one
//
// "Canonical" means exactly the form to_roman produces: the subtractive pairs IV, IX,
// XL, XC, CD, CM, and nothing else that happens to parse. So "IIII", "VV", "LL", "DD",
// "MMMM", "IVI", "ix" and "" are all rejected -- while to_number(to_roman(n)) == n for
// every n in 1..3999.

#include <optional>
#include <string>
#include <string_view>

namespace romanx {

std::optional<std::string> to_roman(long long n);
std::optional<long long> to_number(std::string_view s);

}  // namespace romanx
