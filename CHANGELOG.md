# Changelog

This project follows Semantic Versioning and Keep a Changelog.

## [Unreleased]

## [0.1.0] - 2026-08-02

### Added

- Local-first Python SDK and `portfolio` CLI with an offline deterministic demo.
- C++20 analytics engine and pybind11 extension.
- Portfolio accounting, risk, scenario, ETF exposure, reporting, and data provenance.
- Linux and macOS CI, native tests, sanitizers, packaging checks, and wheel smoke tests.

### Security

- AI explanations are disabled by default and available only through the `ai` extra.
- Scenario YAML uses safe loading; private and generated files are excluded from distributions.

[Unreleased]: https://github.com/stadimeti19/portfolio-intelligence-engine/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/stadimeti19/portfolio-intelligence-engine/releases/tag/v0.1.0
