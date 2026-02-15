# Code Archaeology Kit (Standalone)

This is the standalone version (separate from recon-workbench).

## Why separate
- `recon-workbench` = evidence orchestration platform
- `code-archaeology-kit` = focused git-history intelligence product

## CLI

```bash
python -m code_archaeology scan \
  --repo /path/to/repo \
  --since-days 365 \
  --format both \
  --top-actions 3 \
  --output-dir ./artifacts
```

Outputs:
- `archaeology.json`
- `archaeology_report.md`

Safety / privacy flags:
- `--include-repo-path` (opt-in) include full repo path in `summary.repo_path` (default: basename only).
- `--include-commit-messages` (opt-in) include sanitized commit messages in outputs (default: redacted).

Signal-quality controls:
- `--large-commit-strategy {cap,skip}` for temporal coupling on commits that touch more than `--max-files-per-commit` files (default: `cap`).

## Contract highlights
- deterministic ordering
- explicit overwrite gate (`--force`)
- PII gate (`--include-authors` requires `--ack-pii`)
- bounded analysis (`--max-commits`, `--max-files-per-commit`, `--timeout-seconds`)
- noise filtering (`--ignore-glob` + default ignore rules)
- path classes (`product|test|infra|docs|generated|unknown`)
- coupling classes (`expected|risky|suspicious`)
- confidence explainers and top high-leverage action list

## Competition-led build process
See `docs/competition-matrix.md`.
