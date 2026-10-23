# Your tests go here

Write gtest files (`tests/own/*_test.cpp`) and **add each one to `CMakeLists.txt`**. A file
that is not listed there is never compiled and never run, and nothing tells you:

```cpp
#include <gtest/gtest.h>
#include "bits/bits.hpp"

TEST(Popcount, SmallValues) {
    EXPECT_EQ(bits::popcount(0b1011), 3);
}
```

and in `CMakeLists.txt`, below the marked line:

```cmake
add_executable(own_small tests/own/small_test.cpp)
target_link_libraries(own_small PRIVATE bits GTest::gtest_main)
gtest_discover_tests(own_small)
```

Build and run with `bash tools/run_own_tests.sh`.

Write the cases you would defend: each function's boundaries (0, 1, 2, 31, 32, 33, the top
bit set), and at least one property that has to hold for every input rather than for the
examples you happened to pick.
