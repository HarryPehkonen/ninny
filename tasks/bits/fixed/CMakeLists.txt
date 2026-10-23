# FROZEN -- do not modify the parts above "YOUR TESTS" except to add your test targets
# there. The acceptance corpus appends its own target to this file in a staged copy, and
# checks that everything else is unchanged.
#
# A gtest file that is not listed below is never compiled and never run. Adding a test is
# therefore two steps: write the file, and add its lines here.
cmake_minimum_required(VERSION 3.16)
project(bits LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Debug)
endif()

enable_testing()

# GoogleTest: the distro's own copy, so nothing is downloaded. If CMake cannot find it,
# that is a broken environment, not a broken task -- say so loudly.
find_package(GTest REQUIRED)
include(GoogleTest)

add_library(bits INTERFACE)
target_include_directories(bits INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_options(bits INTERFACE -Wall -Wextra)

# ---------------------------------------------------------------- YOUR TESTS BELOW HERE
# Add one add_executable + target_link_libraries + gtest_discover_tests per test file.
# Example, for tests/own/example_test.cpp:
#
#   add_executable(own_example tests/own/example_test.cpp)
#   target_link_libraries(own_example PRIVATE bits GTest::gtest_main)
#   gtest_discover_tests(own_example)

add_executable(own_bits tests/own/bits_test.cpp)
target_link_libraries(own_bits PRIVATE bits GTest::gtest_main)
gtest_discover_tests(own_bits)
