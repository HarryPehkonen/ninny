# Bit twiddling, as a library

Implement `include/bits/bits.hpp`: a header-only C++17 library. There is no `main`, no
binary and no command line — the whole deliverable is the header.

```cpp
namespace bits {
std::uint32_t popcount(std::uint32_t x);      // number of set bits
std::uint32_t rotl(std::uint32_t x, unsigned n);   // rotate left by n, n in 0..31
std::uint32_t reverse_bits(std::uint32_t x);  // reverse all 32 bits
bool          is_pow2(std::uint32_t x);       // true iff x is 1, 2, 4, ... (0 is not)
std::uint32_t next_pow2(std::uint32_t x);     // smallest power of two >= x; 0 -> 1
}
```

## Rules

- **Header-only.** Everything lives in `bits.hpp`, with no `.cpp` files and no linking.
- **C++17.** No compiler-specific builtins: `__builtin_popcount` and friends are not
  allowed, and neither are `<bit>`'s `std::popcount` or `std::rotl` (they are C++20).
  The point is the algorithm.
- **`next_pow2` only has to be correct for `x <= 2^30`**, so the answer always fits in 32
  bits. Say so in a comment rather than relying on it silently.
- **No allocation, no exceptions.** These are pure functions over unsigned integers.

## Your tests are gtest tests, and CMake must know about each one

`CMakeLists.txt` is frozen and links GoogleTest. **A gtest file that is not added to
`CMakeLists.txt` is never built and never run** — so adding a test file is two steps:
write the file under `tests/own/`, then add its `add_executable` and `gtest_discover_tests`
lines to `CMakeLists.txt`. Nothing warns you if you skip the second step; the suite just
gets smaller. That is exactly what this task is here to measure.

Write the cases you would defend: each function's boundaries (0, 1, 2, 31, 32, 33, the
top bit set), and at least one property that has to hold for every input rather than for
the examples you picked.
