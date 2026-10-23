# Your tests go here

Every `tests/own/*.cpp` is compiled together with every `src/*.cpp` and run by
`tools/run_own_tests.sh`, which is what the `run_tests` action executes.

```cpp
#include "romanx/romanx.hpp"

#include "harness.hpp"

TEST(to_roman_uses_the_subtractive_form) {
  const auto got = romanx::to_roman(4);
  CHECK(got.has_value());
  if (got) CHECK_EQ(*got, std::string("IV"));
}
```

One of the files has to end with `FROZEN_TEST_MAIN("OWN")`, which provides `main()` and
prints the count and the verdict line the runner reports.

A missing `has_value()` is not a compile error, so check it before you dereference: a
`std::optional` that holds nothing will take the whole suite down with it, and a crashed
suite tells you much less than a failing case does.

These cases are the only tests anybody will read when they ask whether the
implementation can be trusted. Write the ones you would want to defend against:
the edges, the rejected input, and at least one property that has to hold for every
value rather than for the examples you happened to pick.
