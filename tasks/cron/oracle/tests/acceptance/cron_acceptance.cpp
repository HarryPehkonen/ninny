// FROZEN acceptance corpus — do not modify, do not delete.
//
// This file is the oracle for the cron kernel. It reads the Schedule bits
// directly, so an implementation that "behaves right" but stores the wrong bits
// fails here.
#include "cronx/cronx.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "../harness.hpp"

using cronx::matches;
using cronx::Minute;
using cronx::next;
using cronx::parse;
using cronx::Schedule;

namespace {

constexpr std::uint64_t mask_bits(int lo, int hi) {
  std::uint64_t m = 0;
  for (int i = lo; i <= hi; ++i) m |= (std::uint64_t{1} << i);
  return m;
}

int bit_count(std::uint64_t v) {
  int n = 0;
  while (v != 0) { n += static_cast<int>(v & 1U); v >>= 1; }
  return n;
}

// Reference minutes used by the day-rule cases (all exact midnights, so the
// minute and hour fields are trivially satisfied).
constexpr Minute midnight(int day) { return static_cast<Minute>(day) * 1440; }
constexpr Minute kEpoch = 0;                       // Thu 1970-01-01 00:00Z
constexpr Minute kFri_1970_01_02_0900 = 1980;      // Fri, 09:00
constexpr Minute kMon_1970_01_05_0900 = 6300;      // Mon, 09:00
constexpr Minute kTue_1970_01_13 = midnight(12);   // Tue 13th, 00:00
constexpr Minute kWed_1970_01_07 = midnight(6);    // Wed 7th, 00:00
constexpr Minute kLeap_1972_02_29 = 1136160;       // Tue 1972-02-29 00:00Z
constexpr Minute kNewYear_1971 = 525600;           // Fri 1971-01-01 00:00Z

const std::uint64_t kAllMinutes = mask_bits(0, 59);
const std::uint64_t kAllHours = mask_bits(0, 23);
const std::uint64_t kAllDom = mask_bits(1, 31);
const std::uint64_t kAllMonths = mask_bits(1, 12);
const std::uint64_t kAllDow = mask_bits(0, 6);

}  // namespace

TEST(parse_accepts_star_fields) {
  const auto r = parse("* * * * *");
  CHECK(r.ok);
  CHECK_EQ(r.schedule.minute, kAllMinutes);
  CHECK_EQ(r.schedule.hour, kAllHours);
  CHECK_EQ(r.schedule.dom, kAllDom);
  CHECK_EQ(r.schedule.month, kAllMonths);
  CHECK_EQ(r.schedule.dow, kAllDow);
}

TEST(parse_star_flags_unrestricted) {
  const auto r = parse("* * * * *");
  CHECK(r.ok);
  CHECK(!r.schedule.dom_restricted);
  CHECK(!r.schedule.dow_restricted);
}

TEST(parse_step_one_is_restricted) {
  // "*/1" selects every value but its text is NOT "*", so the field counts as
  // restricted and the day rule becomes OR. This is the classic Vixie trap.
  const auto stepped = parse("0 0 */1 * FRI");
  CHECK(stepped.ok);
  CHECK(stepped.schedule.dom_restricted);
  CHECK(stepped.schedule.dow_restricted);
  CHECK_EQ(stepped.schedule.dom, kAllDom);
  CHECK(matches(stepped.schedule, kTue_1970_01_13));  // Tuesday: dom matched, OR

  const auto starred = parse("0 0 * * FRI");
  CHECK(starred.ok);
  CHECK(!starred.schedule.dom_restricted);
  CHECK(!matches(starred.schedule, kTue_1970_01_13));  // AND: not Friday
}

TEST(parse_range_and_step_bits) {
  const auto a = parse("0-30/15 * * * *");
  CHECK(a.ok);
  CHECK_EQ(a.schedule.minute, (std::uint64_t{1} << 0) | (std::uint64_t{1} << 15) |
                                  (std::uint64_t{1} << 30));

  const auto b = parse("*/15 * * * *");
  CHECK(b.ok);
  CHECK_EQ(b.schedule.minute, (std::uint64_t{1} << 0) | (std::uint64_t{1} << 15) |
                                  (std::uint64_t{1} << 30) | (std::uint64_t{1} << 45));

  const auto c = parse("5/10 * * * *");
  CHECK(c.ok);
  CHECK_EQ(bit_count(c.schedule.minute), 1);
  CHECK_EQ(c.schedule.minute, std::uint64_t{1} << 5);
}

TEST(parse_list_of_values) {
  const auto a = parse("1,2,3 * * * *");
  CHECK(a.ok);
  CHECK_EQ(a.schedule.minute, (std::uint64_t{1} << 1) | (std::uint64_t{1} << 2) |
                                  (std::uint64_t{1} << 3));

  const auto b = parse("0,10-12/2 * * * *");
  CHECK(b.ok);
  CHECK_EQ(b.schedule.minute, (std::uint64_t{1} << 0) | (std::uint64_t{1} << 10) |
                                  (std::uint64_t{1} << 12));
}

TEST(parse_month_and_weekday_names) {
  const auto a = parse("* * * JAN *");
  CHECK(a.ok);
  CHECK_EQ(a.schedule.month, std::uint64_t{1} << 1);

  const auto b = parse("* * * dec *");
  CHECK(b.ok);
  CHECK_EQ(b.schedule.month, std::uint64_t{1} << 12);

  const auto c = parse("* * * * SAT");
  CHECK(c.ok);
  CHECK_EQ(c.schedule.dow, std::uint64_t{1} << 6);

  const auto d = parse("0 9 * * MON-FRI");
  CHECK(d.ok);
  CHECK_EQ(d.schedule.dow, mask_bits(1, 5));
  CHECK(d.schedule.dow_restricted);
}

TEST(parse_weekday_seven_is_sunday) {
  const auto r = parse("* * * * 7");
  CHECK(r.ok);
  CHECK_EQ(r.schedule.dow, std::uint64_t{1} << 0);
  CHECK_EQ(bit_count(r.schedule.dow), 1);
  CHECK(!matches(r.schedule, kEpoch));           // Thursday 1970-01-01 is not Sunday
  CHECK(matches(r.schedule, midnight(3)));       // Sunday 1970-01-04
}

TEST(parse_rejects_wrong_field_count) {
  for (const std::string& expr : {std::string("* * * *"), std::string("* * * * * *"),
                                 std::string(""), std::string("   ")}) {
    const auto r = parse(expr);
    CHECK(!r.ok);
    CHECK_EQ(r.error_field, static_cast<std::size_t>(5));
  }
}

TEST(parse_rejects_out_of_range_in_every_field) {
  struct Case { const char* expr; std::size_t field; };
  const Case cases[] = {
      {"60 * * * *", 0}, {"* 24 * * *", 1}, {"* * 0 * *", 2},
      {"* * 32 * *", 2}, {"* * * 13 *", 3}, {"* * * * 8", 4},
  };
  for (const Case& c : cases) {
    const auto r = parse(c.expr);
    CHECK(!r.ok);
    CHECK_EQ(r.error_field, c.field);
  }
}

TEST(parse_rejects_step_zero) {
  const auto r = parse("*/0 * * * *");
  CHECK(!r.ok);
  CHECK_EQ(r.error_field, static_cast<std::size_t>(0));
}

TEST(parse_rejects_descending_range) {
  const auto r = parse("10-5 * * * *");
  CHECK(!r.ok);
  CHECK_EQ(r.error_field, static_cast<std::size_t>(0));
}

TEST(parse_rejects_empty_list_element) {
  const auto r = parse("1,,2 * * * *");
  CHECK(!r.ok);
  CHECK_EQ(r.error_field, static_cast<std::size_t>(0));
}

TEST(parse_rejects_unknown_name) {
  const auto a = parse("* * * JAX *");
  CHECK(!a.ok);
  CHECK_EQ(a.error_field, static_cast<std::size_t>(3));

  const auto b = parse("* * * * MON-FRI/2");
  CHECK(!b.ok);
  CHECK_EQ(b.error_field, static_cast<std::size_t>(4));
}

TEST(parse_failure_leaves_schedule_untouched) {
  // A failed parse must not commit a half-built schedule: every bit set and
  // both flags must still have their default values.
  const auto bad = parse("60 * * * *");
  CHECK(!bad.ok);
  CHECK_EQ(bad.schedule.minute, std::uint64_t{0});
  CHECK_EQ(bad.schedule.hour, std::uint64_t{0});
  CHECK_EQ(bad.schedule.dom, std::uint64_t{0});
  CHECK_EQ(bad.schedule.month, std::uint64_t{0});
  CHECK_EQ(bad.schedule.dow, std::uint64_t{0});
  CHECK(!bad.schedule.dom_restricted);
  CHECK(!bad.schedule.dow_restricted);
}

TEST(match_epoch_is_thursday) {
  const auto thu = parse("* * * * THU");
  CHECK(thu.ok);
  CHECK(matches(thu.schedule, kEpoch));

  const auto fri = parse("* * * * FRI");
  CHECK(fri.ok);
  CHECK(!matches(fri.schedule, kEpoch));      // Thursday 1970-01-01
  CHECK(!matches(fri.schedule, kEpoch + 1));  // Thursday 00:01 — still Thursday
  CHECK(matches(fri.schedule, 1440));         // Friday 00:00
}

TEST(match_day_fields_both_restricted_is_or) {
  const auto r = parse("0 0 13 * FRI");
  CHECK(r.ok);
  CHECK(r.schedule.dom_restricted);
  CHECK(r.schedule.dow_restricted);
  CHECK(matches(r.schedule, kTue_1970_01_13));  // the 13th, whatever weekday
  CHECK(matches(r.schedule, 1440));             // Friday the 2nd: dow only
  CHECK(!matches(r.schedule, kWed_1970_01_07)); // 7th, Wednesday: neither
}

TEST(match_day_fields_and_when_one_is_star) {
  const auto dow_only = parse("0 0 * * FRI");
  CHECK(dow_only.ok);
  CHECK(matches(dow_only.schedule, 1440));
  CHECK(!matches(dow_only.schedule, kTue_1970_01_13));

  const auto dom_only = parse("0 0 13 * *");
  CHECK(dom_only.ok);
  CHECK(matches(dom_only.schedule, kTue_1970_01_13));
  CHECK(!matches(dom_only.schedule, 1440));
}

TEST(next_every_fifteen_minutes) {
  const auto r = parse("*/15 * * * *");
  CHECK(r.ok);
  const auto got = next(r.schedule, 0, 4);
  CHECK_EQ(got.size(), static_cast<std::size_t>(4));
  CHECK_EQ(got[0], Minute{15});
  CHECK_EQ(got[1], Minute{30});
  CHECK_EQ(got[2], Minute{45});
  CHECK_EQ(got[3], Minute{60});
}

TEST(next_is_strictly_after_from) {
  const auto r = parse("*/15 * * * *");
  CHECK(r.ok);
  const auto at = next(r.schedule, 15, 1);
  CHECK_EQ(at.size(), static_cast<std::size_t>(1));
  CHECK_EQ(at[0], Minute{30});
  const auto between = next(r.schedule, 16, 1);
  CHECK_EQ(between.size(), static_cast<std::size_t>(1));
  CHECK_EQ(between[0], Minute{30});
  const auto zero = next(r.schedule, 0, 1);
  CHECK_EQ(zero[0], Minute{15});
}

TEST(next_weekday_morning_skips_weekend) {
  const auto r = parse("0 9 * * MON-FRI");
  CHECK(r.ok);
  const auto got = next(r.schedule, kFri_1970_01_02_0900, 1);
  CHECK_EQ(got.size(), static_cast<std::size_t>(1));
  CHECK_EQ(got[0], kMon_1970_01_05_0900);
}

TEST(next_february_29_is_a_leap_year) {
  const auto r = parse("0 0 29 2 *");
  CHECK(r.ok);
  const auto got = next(r.schedule, 0, 1);
  CHECK_EQ(got.size(), static_cast<std::size_t>(1));
  CHECK_EQ(got[0], kLeap_1972_02_29);
}

TEST(next_never_matching_is_empty) {
  const auto r = parse("0 0 30 2 *");
  CHECK(r.ok);
  const auto got = next(r.schedule, 0, 5);
  CHECK_EQ(got.size(), static_cast<std::size_t>(0));
}

TEST(next_respects_search_limit) {
  const auto r = parse("0 0 1 1 *");
  CHECK(r.ok);
  const auto short_search = next(r.schedule, 0, 1, 1440);
  CHECK_EQ(short_search.size(), static_cast<std::size_t>(0));
  const auto long_search = next(r.schedule, 0, 1, 600000);
  CHECK_EQ(long_search.size(), static_cast<std::size_t>(1));
  CHECK_EQ(long_search[0], kNewYear_1971);
}

FROZEN_TEST_MAIN("ACCEPTANCE")