PYTHON ?= python
PYBIND11_DIR := $(shell $(PYTHON) -m pybind11 --cmakedir 2>/dev/null)
PYBIND11_CMAKE_ARGS := -DPython_EXECUTABLE=$(PYTHON) $(if $(PYBIND11_DIR),-Dpybind11_DIR=$(PYBIND11_DIR),)

.PHONY: setup build demo test test-python test-cpp lint format typecheck benchmark clean

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

benchmark:
	cmake -S . -B build/cmake $(PYBIND11_CMAKE_ARGS)
	cmake --build build/cmake --target portfolio_engine_benchmarks
	./build/cmake/portfolio_engine_benchmarks

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache
