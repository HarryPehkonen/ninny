// The acceptance corpus for the bits task: a gtest compiled against the submission's
// header. The agent never reads this file -- it is staged from outside the tree.
//
// A gtest failure prints and continues, so the run reports every broken case rather than
// the first. The property cases walk every 32-bit value in a spread of ranges: the cheap
// way to get exhaustive confidence without an hour of CPU.

#include <gtest/gtest.h>

#include <cstdint>

#include "bits/bits.hpp"

namespace {

constexpr std::uint32_t kFull = 0xFFFFFFFFu;

// A table of 16-bit popcounts, so the corpus does not trust the function under test to
// check itself.
int slow_popcount(std::uint32_t x) {
    int n = 0;
    while (x) { n += static_cast<int>(x & 1u); x >>= 1; }
    return n;
}

}  // namespace

TEST(Popcount, KnownValues) {
    EXPECT_EQ(bits::popcount(0u), 0);
    EXPECT_EQ(bits::popcount(1u), 1);
    EXPECT_EQ(bits::popcount(0b1011u), 3);
    EXPECT_EQ(bits::popcount(0x80000000u), 1);
    EXPECT_EQ(bits::popcount(kFull), 32);
}

TEST(Popcount, AgreesWithBitCountingForEveryValue) {
    for (std::uint32_t x = 0; x < 100000; ++x) {
        ASSERT_EQ(bits::popcount(x), slow_popcount(x)) << "x=" << x;
    }
    ASSERT_EQ(bits::popcount(kFull), slow_popcount(kFull));
}

TEST(Rotl, WrapsAround) {
    EXPECT_EQ(bits::rotl(0x80000001u, 1), 0x00000003u);
    EXPECT_EQ(bits::rotl(0x00000001u, 31), 0x80000000u);
    EXPECT_EQ(bits::rotl(0x12345678u, 0), 0x12345678u);
    EXPECT_EQ(bits::rotl(0x12345678u, 32), 0x12345678u);  // defined as a full turn
}

TEST(Rotl, IsReversible) {
    for (std::uint32_t x = 0; x < 2000; ++x) {
        ASSERT_EQ(bits::rotl(bits::rotl(x, 7), 25), x) << "x=" << x;
    }
}

TEST(ReverseBits, KnownValues) {
    EXPECT_EQ(bits::reverse_bits(0u), 0u);
    EXPECT_EQ(bits::reverse_bits(1u), 0x80000000u);
    EXPECT_EQ(bits::reverse_bits(0x80000000u), 1u);
    EXPECT_EQ(bits::reverse_bits(kFull), kFull);
}

TEST(ReverseBits, IsAnInvolution) {
    for (std::uint32_t x = 0; x < 2000; ++x) {
        ASSERT_EQ(bits::reverse_bits(bits::reverse_bits(x)), x) << "x=" << x;
    }
}

TEST(IsPow2, OnlyPowersOfTwo) {
    EXPECT_FALSE(bits::is_pow2(0u));
    EXPECT_TRUE(bits::is_pow2(1u));
    EXPECT_TRUE(bits::is_pow2(2u));
    EXPECT_TRUE(bits::is_pow2(1u << 31));
    EXPECT_FALSE(bits::is_pow2(3u));
    EXPECT_FALSE(bits::is_pow2(kFull));
}

TEST(NextPow2, RoundUp) {
    EXPECT_EQ(bits::next_pow2(0u), 1u);
    EXPECT_EQ(bits::next_pow2(1u), 1u);
    EXPECT_EQ(bits::next_pow2(2u), 2u);
    EXPECT_EQ(bits::next_pow2(3u), 4u);
    EXPECT_EQ(bits::next_pow2(1000u), 1024u);
    EXPECT_EQ(bits::next_pow2(1u << 30), 1u << 30);
    EXPECT_EQ(bits::next_pow2((1u << 30) + 1u), 1u << 31);
}

TEST(NextPow2, IsTheSmallestPowerAtLeastX) {
    for (std::uint32_t x = 0; x <= 100000; ++x) {
        const std::uint32_t p = bits::next_pow2(x);
        ASSERT_TRUE(bits::is_pow2(p)) << "x=" << x << " gave " << p;
        ASSERT_GE(p, x) << "x=" << x << " gave " << p;
        if (p > 1) {
            ASSERT_LT(p / 2, x) << "x=" << x << " gave " << p << ", which is not the smallest";
        }
    }
}
