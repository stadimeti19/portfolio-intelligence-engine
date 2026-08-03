PYTHON ?= python
PYTHON_EXECUTABLE := $(shell $(PYTHON) -c 'import sys; print(sys.executable)')
PYBIND11_DIR := $(shell $(PYTHON) -m pybind11 --cmakedir 2>/dev/null)
PYBIND11_CMAKE_ARGS := -DPython_EXECUTABLE=$(PYTHON_EXECUTABLE) $(if $(PYBIND11_DIR),-Dpybind11_DIR=$(PYBIND11_DIR),)

.PHONY: setup build demo demo-native test test-python test-cpp lint format typecheck \
	benchmark benchmark-cpp benchmark-python benchmark-report sanitize-address \
	sanitize-undefined sanitize-thread fuzz clean

setup:
	$(PYTHON) -m pip install -e ".[dev]"

build:
	$(PYTHON) -m pip install -e ".[dev]"

demo:
	portfolio doctor
	portfolio summary
	portfolio performance
	portfolio risk
	portfolio scenario run tech-selloff

demo-native:
	cmake -S . -B build/cmake $(PYBIND11_CMAKE_ARGS) -DCMAKE_BUILD_TYPE=Release
	cmake --build build/cmake --target portfolio_engine_demo
	./build/cmake/portfolio-engine-demo

test: test-python test-cpp

test-python:
	$(PYTHON) -m pytest tests

test-cpp:
	cmake -S . -B build/cmake $(PYBIND11_CMAKE_ARGS)
	cmake --build build/cmake
	ctest --test-dir build/cmake --output-on-failure

lint:
	$(PYTHON) -m ruff check src tests

format:
	$(PYTHON) -m ruff format src tests

typecheck:
	$(PYTHON) -m mypy src/portfolio_intelligence

benchmark: benchmark-report

benchmark-cpp:
	cmake -S . -B build/benchmark $(PYBIND11_CMAKE_ARGS) -DCMAKE_BUILD_TYPE=Release \
		-DPORTFOLIO_ENGINE_BUILD_BENCHMARKS=ON
	cmake --build build/benchmark --target portfolio_engine_benchmarks
	./build/benchmark/portfolio_engine_benchmarks --output build/cpp-benchmarks.json

benchmark-python:
	$(PYTHON) benchmarks/python_reference.py --output build/python-benchmarks.json

benchmark-report: benchmark-cpp benchmark-python
	$(PYTHON) benchmarks/compare_results.py build/cpp-benchmarks.json build/python-benchmarks.json

sanitize-address:
	cmake -S . -B build/asan -DPORTFOLIO_ENGINE_BUILD_PYTHON=OFF \
		-DPORTFOLIO_ENGINE_BUILD_BENCHMARKS=OFF -DPORTFOLIO_ENGINE_ENABLE_ASAN=ON
	cmake --build build/asan
	ctest --test-dir build/asan --output-on-failure

sanitize-undefined:
	cmake -S . -B build/ubsan -DPORTFOLIO_ENGINE_BUILD_PYTHON=OFF \
		-DPORTFOLIO_ENGINE_BUILD_BENCHMARKS=OFF -DPORTFOLIO_ENGINE_ENABLE_UBSAN=ON
	cmake --build build/ubsan
	ctest --test-dir build/ubsan --output-on-failure

sanitize-thread:
	cmake -S . -B build/tsan -DPORTFOLIO_ENGINE_BUILD_PYTHON=OFF \
		-DPORTFOLIO_ENGINE_BUILD_BENCHMARKS=OFF -DPORTFOLIO_ENGINE_ENABLE_TSAN=ON
	cmake --build build/tsan
	ctest --test-dir build/tsan --output-on-failure

fuzz:
	cmake -S . -B build/fuzz -DPORTFOLIO_ENGINE_BUILD_PYTHON=OFF \
		-DPORTFOLIO_ENGINE_BUILD_BENCHMARKS=OFF -DPORTFOLIO_ENGINE_BUILD_FUZZ=ON
	cmake --build build/fuzz --target portfolio_engine_fuzz
	./build/fuzz/portfolio_engine_fuzz -max_total_time=30

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache
