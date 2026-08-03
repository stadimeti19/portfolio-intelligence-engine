cmake_minimum_required(VERSION 3.20)
project(portfolio_intelligence_engine VERSION 0.2.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

option(PORTFOLIO_ENGINE_BUILD_PYTHON "Build the pybind11 extension" ON)
option(PORTFOLIO_ENGINE_BUILD_BENCHMARKS "Build native benchmarks" OFF)
option(PORTFOLIO_ENGINE_BUILD_FUZZ "Build libFuzzer targets (Clang only)" OFF)
option(PORTFOLIO_ENGINE_ENABLE_ASAN "Enable AddressSanitizer" OFF)
option(PORTFOLIO_ENGINE_ENABLE_UBSAN "Enable UndefinedBehaviorSanitizer" OFF)
option(PORTFOLIO_ENGINE_ENABLE_TSAN "Enable ThreadSanitizer" OFF)

if(PORTFOLIO_ENGINE_ENABLE_TSAN AND
   (PORTFOLIO_ENGINE_ENABLE_ASAN OR PORTFOLIO_ENGINE_ENABLE_UBSAN))
  message(FATAL_ERROR "ThreadSanitizer must be enabled in a separate build")
endif()

find_package(Threads REQUIRED)

function(portfolio_engine_set_warnings target)
  if(MSVC)
    target_compile_options(${target} PRIVATE /W4 /permissive-)
  else()
    target_compile_options(${target} PRIVATE -Wall -Wextra -Wpedantic -Wconversion -Wshadow)
  endif()
endfunction()

function(portfolio_engine_set_sanitizers target)
  if(PORTFOLIO_ENGINE_ENABLE_ASAN)
    target_compile_options(${target} PRIVATE -fsanitize=address -fno-omit-frame-pointer)
    target_link_options(${target} PRIVATE -fsanitize=address)
  endif()
  if(PORTFOLIO_ENGINE_ENABLE_UBSAN)
    target_compile_options(${target} PRIVATE -fsanitize=undefined -fno-omit-frame-pointer)
    target_link_options(${target} PRIVATE -fsanitize=undefined)
  endif()
  if(PORTFOLIO_ENGINE_ENABLE_TSAN)
    target_compile_options(${target} PRIVATE -fsanitize=thread -fno-omit-frame-pointer)
    target_link_options(${target} PRIVATE -fsanitize=thread)
  endif()
endfunction()

add_library(portfolio_engine_core
  cpp/src/analytics.cpp
  cpp/src/covariance.cpp
  cpp/src/engine.cpp
  cpp/src/incremental_statistics.cpp
  cpp/src/simulation.cpp
)
add_library(portfolio_engine::core ALIAS portfolio_engine_core)
set_target_properties(portfolio_engine_core PROPERTIES POSITION_INDEPENDENT_CODE ON)
target_include_directories(portfolio_engine_core
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/cpp/include>
    $<INSTALL_INTERFACE:include>
)
target_link_libraries(portfolio_engine_core PUBLIC Threads::Threads)
portfolio_engine_set_warnings(portfolio_engine_core)
portfolio_engine_set_sanitizers(portfolio_engine_core)

if(PORTFOLIO_ENGINE_BUILD_PYTHON)
  set(PYBIND11_FINDPYTHON ON)
  find_package(pybind11 CONFIG REQUIRED)
  pybind11_add_module(portfolio_engine_python cpp/bindings/python_bindings.cpp)
  target_link_libraries(portfolio_engine_python PRIVATE portfolio_engine::core)
  target_compile_definitions(portfolio_engine_python PRIVATE PYBIND11_DETAILED_ERROR_MESSAGES)
  set_target_properties(portfolio_engine_python PROPERTIES OUTPUT_NAME portfolio_engine)
  portfolio_engine_set_warnings(portfolio_engine_python)
  portfolio_engine_set_sanitizers(portfolio_engine_python)
  install(TARGETS portfolio_engine_python LIBRARY DESTINATION .)
  install(FILES portfolio_engine.pyi DESTINATION .)
endif()

add_executable(portfolio_engine_demo cpp/apps/engine_demo.cpp)
target_link_libraries(portfolio_engine_demo PRIVATE portfolio_engine::core)
set_target_properties(portfolio_engine_demo PROPERTIES OUTPUT_NAME portfolio-engine-demo)
portfolio_engine_set_warnings(portfolio_engine_demo)
portfolio_engine_set_sanitizers(portfolio_engine_demo)

include(CTest)
if(BUILD_TESTING)
  add_executable(portfolio_engine_tests cpp/tests/analytics_tests.cpp)
  target_link_libraries(portfolio_engine_tests PRIVATE portfolio_engine::core)
  portfolio_engine_set_warnings(portfolio_engine_tests)
  portfolio_engine_set_sanitizers(portfolio_engine_tests)
  add_test(NAME portfolio_engine_tests COMMAND portfolio_engine_tests)
endif()

if(PORTFOLIO_ENGINE_BUILD_BENCHMARKS)
  add_executable(portfolio_engine_benchmarks cpp/benchmarks/analytics_benchmark.cpp)
  target_link_libraries(portfolio_engine_benchmarks PRIVATE portfolio_engine::core)
  portfolio_engine_set_warnings(portfolio_engine_benchmarks)
  portfolio_engine_set_sanitizers(portfolio_engine_benchmarks)
endif()

if(PORTFOLIO_ENGINE_BUILD_FUZZ)
  if(NOT CMAKE_CXX_COMPILER_ID MATCHES "Clang")
    message(FATAL_ERROR "The bundled fuzz target requires Clang and libFuzzer")
  endif()
  add_executable(portfolio_engine_fuzz cpp/fuzz/fuzz_engine.cpp)
  target_link_libraries(portfolio_engine_fuzz PRIVATE portfolio_engine::core)
  target_compile_options(portfolio_engine_core PRIVATE -fsanitize=fuzzer-no-link,address
                                                       -fno-omit-frame-pointer)
  target_compile_options(portfolio_engine_fuzz PRIVATE -fsanitize=fuzzer,address
                                                        -fno-omit-frame-pointer)
  target_link_options(portfolio_engine_fuzz PRIVATE -fsanitize=fuzzer,address)
  portfolio_engine_set_warnings(portfolio_engine_fuzz)
endif()
