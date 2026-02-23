# Validation and checks

## Required checks (in order)
1. Verify commands exist in this repo (README/pyproject/package scripts).
2. Run checks that match installed tooling.
3. Stop at first hard failure, fix, and re-run.

## Commands and expected results
- `python3 -m pip install -e .` (install)
- `python3 scripts/check_readability.py README.md` (PASS expected)
- `python3 -m pytest -q` (if pytest installed)
- `python3 -m code_archaeology.cli --help` or `cak scan --help` (CLI help works)
- `npm run docs:lint` (if npm available)

## Known environment gaps (observed)
- `pytest` is not installed (`python3 -m pytest` fails: module missing).
- `npm` is not installed.
