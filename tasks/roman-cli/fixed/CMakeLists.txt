# FROZEN -- the build the task ships with. Do not modify.
#
# Two targets, from the same sources:
#   roman      the command line (src/main.cpp + src/romanx.cpp)
#   own_tests  your suite (src/*.cpp + every tests/own/*.cpp)
#
# C++17, with the warnings the spec froze promoted to errors: under this build a warning
# is a finding, not a suggestion.
cmake_minimum_required(VERSION 3.16)
project(romanx CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_compile_options(-Wall -Wextra -Wpedantic -Werror)

add_library(romanx_lib STATIC src/romanx.cpp)
target_include_directories(romanx_lib PUBLIC include)

add_executable(roman src/main.cpp)
target_link_libraries(roman PRIVATE romanx_lib)

# Globbed on purpose: the suite is whichever cases exist right now, and the build must not
# need editing every time a case file is added. An empty glob is not an error here -- the
# test runner refuses an empty suite before it ever reaches CMake.
file(GLOB OWN_TESTS CONFIGURE_DEPENDS tests/own/*.cpp)
if(OWN_TESTS)
  add_executable(own_tests ${OWN_TESTS})
  target_link_libraries(own_tests PRIVATE romanx_lib)
  target_include_directories(own_tests PRIVATE tests)
endif()
