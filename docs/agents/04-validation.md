# Validation and checks

## Required checks (in order)

1. Verify commands exist in repo docs/config (`README.md`, `pyproject.toml`, `package.json`).
2. Run checks that match available tooling.
3. Stop at first hard failure, fix, then re-run.

## Commands

- `python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"`
- `python3 scripts/check_readability.py README.md`
- `PYTHONPATH=src python3 -m code_archaeology scan --help`
- `npm test`
- `npm run test:deep`
- `npm run docs:lint`

## Observed results (2026-03-05)

- `.venv/bin/python -m pip install -e ".[dev]"` succeeds for editable install with test deps.
- `PYTHONPATH=src python3 -m code_archaeology scan --help` succeeds.
- `npm test` succeeds (uses `.venv` Python when available).
- `npm run test:deep` succeeds and writes artifacts under `artifacts/test`.
- `npm run docs:lint` succeeds when markdown files pass lint rules.
