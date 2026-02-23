# Code Archaeology Report

## Summary
- Repository: `code-archaeology-kit`
- Head commit: `31f330db1dca22c1960c86550bf3ea15e3bd9263`
- Window: last 30 days
- Total commits: 5
- Generated (UTC): 2026-02-23T00:01:27+00:00

## Notices
- `REPO_PATH_REDACTED`: summary.repo_path is redacted to basename by default (use --include-repo-path to include full path).
- `COMMIT_MESSAGES_REDACTED`: Commit messages are redacted by default (use --include-commit-messages to include sanitized messages).

## Signal Quality
- Ignore rules applied:
  - `**/*.pyc`
  - `**/__pycache__/**`
  - `*.lock`
  - `*.pyc`
  - `.venv/**`
  - `__pycache__/**`
  - `build/**`
  - `coverage/**`
  - `dist/**`
  - `node_modules/**`
  - `target/**`
  - `venv/**`

## Top High-Leverage Actions
- [high] **review_temporal_coupling** `README.md <-> src/code_archaeology/analyze.py` (effort=medium, leverage=high) — co-change=3, ratio=1.0, class=risky
- [high] **review_temporal_coupling** `README.md <-> src/code_archaeology/cli.py` (effort=medium, leverage=high) — co-change=3, ratio=1.0, class=risky
- [high] **review_temporal_coupling** `src/code_archaeology/analyze.py <-> tests/test_scan.py` (effort=medium, leverage=high) — co-change=3, ratio=1.0, class=risky

## Abandoned structures

## Temporal coupling
- `README.md` <-> `src/code_archaeology/analyze.py` (co-changes=3, ratio=1.0, class=risky)
- `README.md` <-> `src/code_archaeology/cli.py` (co-changes=3, ratio=1.0, class=risky)
- `src/code_archaeology/analyze.py` <-> `tests/test_scan.py` (co-changes=3, ratio=1.0, class=risky)
- `src/code_archaeology/cli.py` <-> `tests/test_scan.py` (co-changes=3, ratio=1.0, class=risky)
- `README.md` <-> `tests/test_scan.py` (co-changes=3, ratio=1.0, class=expected)
- `src/code_archaeology/analyze.py` <-> `src/code_archaeology/cli.py` (co-changes=3, ratio=1.0, class=expected)

## Coupling classes
- suspicious: 0
- risky: 4
- expected: 2

## Era segmentation
- 2026-02: expansion (5 commits)
