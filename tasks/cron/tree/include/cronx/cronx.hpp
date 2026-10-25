#pragma once
// FROZEN API — the interface is fixed. Implement it in src/, change nothing here.
//
// A cron expression in the classic 5-field form:
//
//     minute hour day-of-month month day-of-week
//
// All time is UTC expressed as MINUTES SINCE THE UNIX EPOCH. There are no
// timezones and no daylight saving in this project, by design: the arithmetic
// must be exact and reproducible.

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace cronx {

using Minute = std::int64_t;

// A parsed schedule as five sets of allowed values.
struct Schedule {
  std::uint64_t minute = 0;  // bit i set  <=>  minute i matches, i in 0..59
  std::uint64_t hour = 0;    // bit i set  <=>  hour   i matches, i in 0..23
  std::uint64_t dom = 0;     // bit i set  <=>  day    i matches, i in 1..31
  std::uint64_t month = 0;   // bit i set  <=>  month  i matches, i in 1..12
  std::uint64_t dow = 0;     // bit i set  <=>  weekday i matches, 0=Sunday..6
  // A field is "restricted" iff its text was not exactly "*".
  bool dom_restricted = false;
  bool dow_restricted = false;
};

struct ParseResult {
  bool ok = false;
  Schedule schedule;         // only meaningful when ok
  std::size_t error_field = 0;  // 0=minute 1=hour 2=dom 3=month 4=dow
  std::string error;         // free text; contents are NOT pinned
};

// Parses "m h dom mon dow" (separated by spaces or tabs, surrounding
// whitespace allowed). Never throws. On failure schedule is untouched.
ParseResult parse(const std::string& expression);

// True if `when` satisfies the schedule, applying the day-of-month /
// day-of-week rule described in SPEC.md.
bool matches(const Schedule& schedule, Minute when);

// Up to `count` matching minutes, strictly after `from`, in ascending order.
// Gives up (returning fewer than `count`, possibly none) if it has scanned
// `search_limit` minutes past `from`.
std::vector<Minute> next(const Schedule& schedule, Minute from,
                         std::size_t count,
                         std::int64_t search_limit = 1000LL * 24 * 60);

}  // namespace cronx