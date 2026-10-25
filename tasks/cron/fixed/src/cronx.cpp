// Reference (control-arm) implementation of the frozen cron API.
#include "cronx/cronx.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace cronx {
namespace {

constexpr std::int64_t kMinutesPerDay = 1440;
constexpr std::int64_t kEpochWeekday = 4;  // 1970-01-01 was a Thursday

const char* const kMonthNames[12] = {"JAN", "FEB", "MAR", "APR", "MAY", "JUN",
                                     "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"};
const char* const kDayNames[7] = {"SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"};

struct FieldSpec {
  int lo;
  int hi;
  const char* const* names;
  std::size_t name_count;
  bool week;  // day-of-week: input value 7 means Sunday
};

const FieldSpec kMinuteField{0, 59, nullptr, 0, false};
const FieldSpec kHourField{0, 23, nullptr, 0, false};
const FieldSpec kDomField{1, 31, nullptr, 0, false};
const FieldSpec kMonthField{1, 12, kMonthNames, 12, false};
const FieldSpec kDowField{0, 7, kDayNames, 7, true};

bool is_space(char c) { return c == ' ' || c == '\t'; }

bool is_digit(char c) { return c >= '0' && c <= '9'; }

char upper(char c) {
  if (c >= 'a' && c <= 'z') return static_cast<char>(c - 'a' + 'A');
  return c;
}

std::string upper_copy(const std::string& s) {
  std::string out;
  out.reserve(s.size());
  for (char c : s) out.push_back(upper(c));
  return out;
}

bool parse_uint(const std::string& text, int& out) {
  if (text.empty()) return false;
  std::int64_t value = 0;
  for (char c : text) {
    if (!is_digit(c)) return false;
    value = value * 10 + (c - '0');
    if (value > 1000000) return false;  // far beyond any field range
  }
  out = static_cast<int>(value);
  return true;
}

int name_value(const std::string& token, const FieldSpec& spec) {
  if (spec.names == nullptr || token.size() != 3) return -1;
  const std::string up = upper_copy(token);
  for (std::size_t i = 0; i < spec.name_count; ++i) {
    const char* candidate = spec.names[i];
    if (up.size() == 3 && up[0] == candidate[0] && up[1] == candidate[1] &&
        up[2] == candidate[2]) {
      return static_cast<int>(i) + spec.lo;
    }
  }
  return -1;
}

bool has_alpha(const std::string& text) {
  for (char c : text) {
    if (!is_digit(c) && c != '-' && c != '*' && c != '/') return true;
  }
  return false;
}

// A numeric value, or a three-letter name when the field allows names.
bool value_of(const std::string& token, const FieldSpec& spec, int& out) {
  if (parse_uint(token, out)) return true;
  const int named = name_value(token, spec);
  if (named < 0) return false;
  out = named;
  return true;
}

void set_bit(std::uint64_t& bits, int value, const FieldSpec& spec) {
  int normalized = value;
  if (spec.week && normalized == 7) normalized = 0;  // 7 means Sunday
  bits |= (std::uint64_t{1} << static_cast<unsigned>(normalized));
}

std::vector<std::string> split(const std::string& text, char sep) {
  std::vector<std::string> parts;
  std::string current;
  for (char c : text) {
    if (c == sep) {
      parts.push_back(current);
      current.clear();
    } else {
      current.push_back(c);
    }
  }
  parts.push_back(current);
  return parts;
}

// One comma-separated item: "*", "N", "A-B", any of those with "/S".
bool parse_item(const std::string& item, const FieldSpec& spec,
                std::uint64_t& bits) {
  if (item.empty()) return false;

  int step = 0;
  std::string base = item;
  const std::size_t slash = item.find('/');
  if (slash != std::string::npos) {
    base = item.substr(0, slash);
    if (item.find('/', slash + 1) != std::string::npos) return false;
    if (base.empty()) return false;
    if (!parse_uint(item.substr(slash + 1), step)) return false;
    if (step < 1) return false;
    if (has_alpha(base)) return false;  // a step on a name is not allowed
  }
  if (base.empty()) return false;

  if (base == "*") {
    const int stride = step == 0 ? 1 : step;
    for (int value = spec.lo; value <= spec.hi; value += stride) {
      set_bit(bits, value, spec);
    }
    return true;
  }

  const std::size_t dash = base.find('-');
  if (dash != std::string::npos) {
    const std::string first = base.substr(0, dash);
    const std::string last = base.substr(dash + 1);
    if (first.empty() || last.empty()) return false;
    if (last.find('-') != std::string::npos) return false;
    int low = 0;
    int high = 0;
    if (!value_of(first, spec, low)) return false;
    if (!value_of(last, spec, high)) return false;
    if (low > high) return false;
    if (low < spec.lo || high > spec.hi) return false;
    const int stride = step == 0 ? 1 : step;
    for (int value = low; value <= high; value += stride) {
      set_bit(bits, value, spec);
    }
    return true;
  }

  int single = 0;
  if (!value_of(base, spec, single)) return false;
  if (single < spec.lo || single > spec.hi) return false;
  set_bit(bits, single, spec);
  return true;
}

bool parse_field(const std::string& text, const FieldSpec& spec,
                 std::uint64_t& bits, bool& restricted) {
  bits = 0;
  restricted = (text != "*");
  if (text.empty()) return false;
  for (const std::string& item : split(text, ',')) {
    if (!parse_item(item, spec, bits)) return false;
  }
  return true;
}

// Hinnant's civil-from-days: turn days since 1970-01-01 into a calendar date.
void civil_from_days(std::int64_t days, int& year, int& month, int& day) {
  const std::int64_t z = days + 719468;
  const std::int64_t era = (z >= 0 ? z : z - 146096) / 146097;
  const std::int64_t doe = z - era * 146097;
  const std::int64_t yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
  const std::int64_t y = yoe + era * 400;
  const std::int64_t doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
  const std::int64_t mp = (5 * doy + 2) / 153;
  day = static_cast<int>(doy - (153 * mp + 2) / 5 + 1);
  month = static_cast<int>(mp + (mp < 10 ? 3 : -9));
  year = static_cast<int>(y + (month <= 2 ? 1 : 0));
}

bool bit_set(std::uint64_t bits, int index) {
  return (bits & (std::uint64_t{1} << static_cast<unsigned>(index))) != 0;
}

bool fields_ok(const std::vector<std::string>& fields) {
  return fields.size() == 5;
}

}  // namespace

ParseResult parse(const std::string& expression) {
  ParseResult result;

  std::vector<std::string> fields;
  std::string current;
  bool seen = false;
  for (char c : expression) {
    if (is_space(c)) {
      if (seen) fields.push_back(current);
      current.clear();
      seen = false;
    } else {
      current.push_back(c);
      seen = true;
    }
  }
  if (seen) fields.push_back(current);

  if (!fields_ok(fields)) {
    result.ok = false;
    result.error_field = 5;
    result.error = "expected exactly five fields";
    return result;
  }

  Schedule schedule;
  const FieldSpec* specs[5] = {&kMinuteField, &kHourField, &kDomField,
                               &kMonthField, &kDowField};
  std::uint64_t* targets[5] = {&schedule.minute, &schedule.hour, &schedule.dom,
                               &schedule.month, &schedule.dow};

  for (std::size_t i = 0; i < 5; ++i) {
    bool restricted = false;
    if (!parse_field(fields[i], *specs[i], *targets[i], restricted)) {
      result.ok = false;
      result.error_field = i;
      result.error = "invalid field value";
      return result;  // schedule is a local, so nothing is committed
    }
    if (i == 2) schedule.dom_restricted = restricted;
    if (i == 4) schedule.dow_restricted = restricted;
  }

  result.ok = true;
  result.schedule = schedule;
  return result;
}

bool matches(const Schedule& schedule, Minute when) {
  if (when < 0) return false;
  const std::int64_t days = when / kMinutesPerDay;
  const std::int64_t minute_of_day = when % kMinutesPerDay;
  const int minute = static_cast<int>(minute_of_day % 60);
  const int hour = static_cast<int>(minute_of_day / 60);

  int year = 0;
  int month = 0;
  int day = 0;
  civil_from_days(days, year, month, day);
  (void)year;

  const int weekday = static_cast<int>((days + kEpochWeekday) % 7);

  if (!bit_set(schedule.minute, minute)) return false;
  if (!bit_set(schedule.hour, hour)) return false;
  if (!bit_set(schedule.month, month)) return false;

  const bool dom_ok = bit_set(schedule.dom, day);
  const bool dow_ok = bit_set(schedule.dow, weekday);
  if (schedule.dom_restricted && schedule.dow_restricted) return dom_ok || dow_ok;
  return dom_ok && dow_ok;
}

std::vector<Minute> next(const Schedule& schedule, Minute from,
                         std::size_t count, std::int64_t search_limit) {
  std::vector<Minute> found;
  if (count == 0 || search_limit <= 0) return found;
  Minute when = from;
  for (std::int64_t scanned = 0; scanned < search_limit; ++scanned) {
    ++when;
    if (matches(schedule, when)) {
      found.push_back(when);
      if (found.size() >= count) break;
    }
  }
  return found;
}

}  // namespace cronx