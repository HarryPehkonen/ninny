#include <gtest/gtest.h>
#include "bits/bits.hpp"

TEST(Popcount, KnownValues) { EXPECT_EQ(bits::popcount(0b1011u), 3); }
TEST(Popcount, Zero) { EXPECT_EQ(bits::popcount(0u), 0); }
TEST(Rotl, Wraps) { EXPECT_EQ(bits::rotl(0x80000001u, 1), 0x00000003u); }
TEST(ReverseBits, One) { EXPECT_EQ(bits::reverse_bits(1u), 0x80000000u); }
TEST(IsPow2, Boundaries) { EXPECT_FALSE(bits::is_pow2(0u)); EXPECT_TRUE(bits::is_pow2(1u << 31)); }
TEST(NextPow2, Rounds) { EXPECT_EQ(bits::next_pow2(0u), 1u); EXPECT_EQ(bits::next_pow2(1000u), 1024u); }
