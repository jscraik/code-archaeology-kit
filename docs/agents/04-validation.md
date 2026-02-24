# Validation and checks

## Required checks (in order)

1. Verify commands exist in repo docs/config (`README.md`, `pyproject.toml`, `package.json`).
2. Run checks that match available tooling.
3. Stop at first hard failure, fix, then re-run.

## Commands

- `python3 -m pip install -e .`
- `python3 scripts/check_readability.py README.md`
- `python3 -m pytest -q`
- `PYTHONPATH=src python3 -m code_archaeology scan --help`
- `npm run docs:lint`

## Observed results (2026-02-24)

- `python3 -m pip install -e .` fails with system `pip 21.2.4` (editable install unsupported for this `pyproject.toml` setup).
- `python3 -m pip install .` succeeds as fallback.
- `python3 -m pytest -q` fails because `pytest` is not installed in the active Python environment.
- `PYTHONPATH=src python3 -m code_archaeology scan --help` succeeds.
- `npm run docs:lint` succeeds when markdown files pass lint rules.
