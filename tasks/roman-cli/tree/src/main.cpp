// FROZEN -- this is the command line the tool presents. Implement src/romanx.cpp,
// not this file: argument parsing is deliberately not part of the exercise.
//
//   roman to-roman <n>     print the canonical numeral            exit 0
//   roman to-number <s>    print its value                        exit 0
//   anything else          usage on stderr                        exit 2
//   input the contract rejects   a message on stderr              exit 1
#include <cstdlib>
#include <exception>
#include <iostream>
#include <optional>
#include <string>

#include "romanx/romanx.hpp"

namespace {

int usage() {
  std::cerr << "usage: roman to-roman <n>      the canonical numeral for 1..3999\n"
               "       roman to-number <s>     the value of a canonical numeral\n";
  return 2;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 3) return usage();
  const std::string mode = argv[1];
  const std::string arg = argv[2];

  if (mode == "to-roman") {
    if (arg.empty() || arg.find_first_not_of("0123456789") != std::string::npos) {
      std::cerr << "roman: " << arg << " is not a decimal integer\n";
      return 1;
    }
    long long n = 0;
    try {
      n = std::stoll(arg);
    } catch (const std::exception&) {
      std::cerr << "roman: " << arg << " is too large to be a number here\n";
      return 1;
    }
    const std::optional<std::string> out = romanx::to_roman(n);
    if (!out) {
      std::cerr << "roman: " << n << " is not in 1..3999\n";
      return 1;
    }
    std::cout << *out << "\n";
    return 0;
  }

  if (mode == "to-number") {
    const std::optional<long long> value = romanx::to_number(arg);
    if (!value) {
      std::cerr << "roman: \"" << arg << "\" is not a canonical numeral\n";
      return 1;
    }
    std::cout << *value << "\n";
    return 0;
  }

  return usage();
}
