cmake_minimum_required(VERSION 3.20)
project(portfolio_intelligence_engine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include_directories(cpp/include)

add_library(portfolio_engine_core
  cpp/src/analytics.cpp
)
set_target_properties(portfolio_engine_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(portfolio_engine_core PUBLIC cpp/include)

set(PYBIND11_FINDPYTHON ON)
find_package(pybind11 CONFIG REQUIRED)
pybind11_add_module(portfolio_engine cpp/bindings/python_bindings.cpp)
target_link_libraries(portfolio_engine PRIVATE portfolio_engine_core)
install(TARGETS portfolio_engine LIBRARY DESTINATION .)
install(FILES portfolio_engine.pyi DESTINATION .)

include(CTest)
if(BUILD_TESTING)
  add_executable(portfolio_engine_tests cpp/tests/analytics_tests.cpp)
  target_link_libraries(portfolio_engine_tests PRIVATE portfolio_engine_core)
  add_test(NAME portfolio_engine_tests COMMAND portfolio_engine_tests)
endif()

add_executable(portfolio_engine_benchmarks cpp/benchmarks/analytics_benchmark.cpp)
target_link_libraries(portfolio_engine_benchmarks PRIVATE portfolio_engine_core)
