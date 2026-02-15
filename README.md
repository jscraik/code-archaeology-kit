# Code Archaeology Kit (Standalone)

Standalone CLI that scans a git repository and produces **actionable, privacy-safe** “what to look at next” archaeology artifacts (high-churn files, temporal coupling pairs, stale/abandoned structures).

## When to use
Use this tool when you want fast, bounded git-history intelligence for a repo (especially to find risky co-change patterns and high-leverage cleanup targets).

## Why separate
- `recon-workbench` = evidence orchestration platform
- `code-archaeology-kit` = focused git-history intelligence product

## Install

```bash
python -m pip install -e .
```

## Quickstart

```bash
cak scan \
  --repo /path/to/repo \
  --since-days 365 \
  --format both \
  --top-actions 3 \
  --share-snippet \
  --output-dir ./artifacts
```

```bash
# Run-from-source (no install needed):
PYTHONPATH=src python -m code_archaeology scan \
  --repo /path/to/repo \
  --since-days 365 \
  --format both \
  --top-actions 3 \
  --share-snippet \
  --output-dir ./artifacts
```

## Outputs
- `archaeology.json`
- `archaeology_report.md`
- (optional) `archaeology_share.md` (when `--share-snippet` is set) — paste into Slack/PR comments (respects `--include-repo-path`)
- (optional) `archaeology_events.jsonl` (when `--share-snippet` is set) — local JSONL event log

## Safety / privacy flags
- `--include-repo-path` (opt-in) include full repo path in `summary.repo_path` (default: basename only).
- `--include-commit-messages` (opt-in) include sanitized commit messages in outputs (default: redacted).
- `--include-authors` (opt-in) requires `--ack-pii`.

## Measurement hook (local)
- Event: `share_snippet_generated` (appends one line to `archaeology_events.jsonl` per run)

## Signal-quality controls
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

## Verify

After a successful run you should see:

- `artifacts/archaeology.json`
- `artifacts/archaeology_report.md`
- (optional) `artifacts/archaeology_share.md` (if `--share-snippet`)

## Troubleshooting

- **`error: Not a git repo: ...`**: pass a path that contains a `.git/` directory.
- **`Refusing overwrite: ... (use --force)`**: add `--force` when re-running into the same `--output-dir`.
- **`error: --include-authors requires --ack-pii`**: add `--ack-pii` or omit `--include-authors`.
- **`error: git not found`**: install `git` and ensure it is on your `PATH`.

## Competition-led build process
See `docs/competition-matrix.md`.

## Contributing / security

- Contributing guide: `CONTRIBUTING.md`
- Security policy: `SECURITY.md`
- Code of conduct: `CODE_OF_CONDUCT.md`

## Project info

- Maintainer: @jscraik
- Last updated: 2026-02-15
- License: Apache-2.0
