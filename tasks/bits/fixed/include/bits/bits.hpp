// A reference implementation of the bits task -- the answer key.
//
// It exists for one reason: to prove the acceptance corpus can pass. An oracle that only
// ever fails proves nothing, so this file is staged into `fixed/` and the corpus is run
// against it before a model is allowed to see the task.

#pragma once

#include <cstdint>

namespace bits {

inline std::uint32_t popcount(std::uint32_t x) {
    // Kernighan's method: clear the lowest set bit until there are none.
    std::uint32_t n = 0;
    while (x) {
        x &= x - 1;
        ++n;
    }
    return n;
}

inline std::uint32_t rotl(std::uint32_t x, unsigned n) {
    n &= 31u;  // a full turn is no turn, and 32 is defined as 0 above
    if (n == 0) return x;
    return (x << n) | (x >> (32u - n));
}

inline std::uint32_t reverse_bits(std::uint32_t x) {
    // The classic five-step swap: halves, nibbles, pairs, single bits.
    x = ((x >> 1) & 0x55555555u) | ((x & 0x55555555u) << 1);
    x = ((x >> 2) & 0x33333333u) | ((x & 0x33333333u) << 2);
    x = ((x >> 4) & 0x0F0F0F0Fu) | ((x & 0x0F0F0F0Fu) << 4);
    x = ((x >> 8) & 0x00FF00FFu) | ((x & 0x00FF00FFu) << 8);
    return (x >> 16) | (x << 16);
}

inline bool is_pow2(std::uint32_t x) {
    return x != 0 && (x & (x - 1)) == 0;
}

// Correct for x <= 2^30 by contract, so the answer always fits in 32 bits. Spreading the
// set bits downward fills in every bit below the highest one, then adding one carries into
// the next power of two.
inline std::uint32_t next_pow2(std::uint32_t x) {
    if (x <= 1) return 1;
    --x;
    x |= x >> 1;
    x |= x >> 2;
    x |= x >> 4;
    x |= x >> 8;
    x |= x >> 16;
    return x + 1;
}

}  // namespace bits
