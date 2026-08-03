# Contributing

Thank you for improving Portfolio Intelligence. By participating, you agree to follow the Code of Conduct.

## Development setup

Requirements: Python 3.11–3.13, a C++20 compiler, CMake 3.20+, and Make. On macOS use current Xcode command-line tools; on Linux use GCC or Clang with pthread support.

```bash
git clone https://github.com/stadimeti19/portfolio-intelligence-engine.git
cd portfolio-intelligence-engine
python -m venv .venv
source .venv/bin/activate
make setup
make test
make demo
```

Before a pull request, run `make lint`, `make typecheck`, `make test`, and `make package`. Add tests for behavioral changes. Financial formulas need a cited methodology, explicit conventions, edge-case tests, and comparison with an independent reference. Benchmark changes must record hardware, OS, compiler, Python, dependencies, workload, warmups, repetitions, statistic, and raw JSON results. Never commit private portfolios, credentials, databases, caches, or generated reports.
