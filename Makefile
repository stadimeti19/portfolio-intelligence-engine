.PHONY: setup build demo test test-python test-cpp lint format typecheck benchmark clean

setup:
	python -m pip install -e ".[dev]"

build:
	python -m pip install -e ".[dev]"

demo:
	portfolio doctor
	portfolio summary
	portfolio performance
	portfolio risk
	portfolio scenario run tech-selloff

test: test-python test-cpp

test-python:
	python -m pytest tests

test-cpp:
	cmake -S . -B build/cmake
	cmake --build build/cmake
	ctest --test-dir build/cmake --output-on-failure

lint:
	python -m ruff check src tests

format:
	python -m ruff format src tests

typecheck:
	python -m mypy src/portfolio_intelligence

benchmark:
	cmake -S . -B build/cmake
	cmake --build build/cmake --target portfolio_engine_benchmarks
	./build/cmake/portfolio_engine_benchmarks

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache

