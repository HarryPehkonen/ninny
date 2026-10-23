// Implement this file.
//
// CMakeLists.txt and tools/ are frozen. Everything you write goes here and in tests/own/.
//
// The stub compiles as it is: a header-only library needs no main, so a suite can be built
// and run against this before a single function is correct. Every answer below is wrong.

#pragma once

#include <cstdint>

namespace bits {

inline std::uint32_t popcount(std::uint32_t x) {
    (void)x;
    return 0;
}

inline std::uint32_t rotl(std::uint32_t x, unsigned n) {
    (void)x;
    (void)n;
    return 0;
}

inline std::uint32_t reverse_bits(std::uint32_t x) {
    (void)x;
    return 0;
}

inline bool is_pow2(std::uint32_t x) {
    (void)x;
    return false;
}

inline std::uint32_t next_pow2(std::uint32_t x) {
    (void)x;
    return 0;
}

}  // namespace bits
