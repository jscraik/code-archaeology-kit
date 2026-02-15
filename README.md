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
