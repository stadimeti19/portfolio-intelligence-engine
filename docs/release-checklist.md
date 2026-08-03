# Release checklist

The version source of truth is `[project].version` in `pyproject.toml`; CMake must match it. Releases use Semantic Versioning.

## Before tagging

- [ ] Working tree contains only reviewed release changes.
- [ ] `make lint`, `make typecheck`, `make test`, `make benchmark`, `make demo`, and `make package` pass.
- [ ] GitHub CI passes on Python 3.11–3.13 for Linux and macOS.
- [ ] Release-artifact workflow produces all expected Linux/macOS wheels and an sdist.
- [ ] Wheel smoke test imports `portfolio_engine` and runs help, doctor, and JSON demo summary.
- [ ] Artifact manifests contain no credentials, private data, databases, caches, reports, logs, or build output.
- [ ] `CHANGELOG.md` and `RELEASE_NOTES.md` match the tag.
- [ ] TestPyPI install is tested in a new environment.
- [ ] Security advisories and dependency alerts are reviewed.

## Publication commands (never run by automation in this repository)

```bash
git tag -s v0.1.0 -m "Portfolio Intelligence 0.1.0"
git push origin v0.1.0

python -m twine upload --repository testpypi dist/*
python -m venv /tmp/portfolio-testpypi
/tmp/portfolio-testpypi/bin/pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ portfolio-intelligence==0.1.0
/tmp/portfolio-testpypi/bin/portfolio doctor

python -m twine upload dist/*
```

Prefer PyPI trusted publishing for the final project configuration; if Twine credentials are used, supply them through the environment/keyring and never command-line arguments or repository files.
