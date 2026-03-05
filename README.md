# Code Archaeology Kit (Standalone)

This is a standalone CLI tool. It scans a git repository to produce actionable archaeology artifacts. These artifacts are privacy-safe. They tell you what to look at next. Artifacts include high-churn files, temporal coupling pairs, and abandoned structures.

## When to use

Use this tool when you want fast, bounded git-history intelligence for a repo. It helps find risky co-change patterns and high-leverage cleanup targets.

## Why separate

- `recon-workbench` = evidence orchestration platform.
- `code-archaeology-kit` = focused git-history intelligence product.

## Install

```bash
python -m pip install -e .
```

### Developer install (includes test tooling)

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
```

## Quickstart

```bash
cak scan \
  --repo /path/to/repo \
  --since-days 365 \
  --format both \
  --top-actions 3 \
  --adaptive-mode shadow \
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
  --adaptive-mode shadow \
  --share-snippet \
  --output-dir ./artifacts
```

## Outputs

- `archaeology.json`.
- `archaeology_report.md`.
- (optional) `archaeology_share.md` (when `--share-snippet` is set) — paste into Slack/PR comments.
- (optional) `archaeology_events.jsonl` (when `--share-snippet` is set) — local JSONL event log.

## Safety / privacy flags

- `--include-repo-path` (opt-in) include full repo path in `summary.repo_path` (default: basename only).
- `--include-commit-messages` (opt-in) include sanitized commit messages in outputs (default: redacted).
- `--include-authors` (opt-in) requires `--ack-pii`.

## Measurement hook (local)

- Event: `share_snippet_generated` (appends one line to `archaeology_events.jsonl` per run)

## Signal-quality controls

- `--large-commit-strategy {cap,skip}` configures temporal coupling for large commits. Use it for commits that touch more than `--max-files-per-commit` files. Default is `cap`.
- `--adaptive-mode {disabled,shadow,adaptive}` controls adaptive top-action ranking against a baseline artifact.
  - `disabled` (default): raw top actions.
  - `shadow`: computes adaptive order in `actionability.shadow_top_actions` while leaving `top_actions` unchanged.
  - `adaptive`: applies adaptive reranking to `top_actions`.
- `--adaptive-baseline-artifact /path/to/archaeology.json` sets explicit baseline source. By default, adaptive modes use `<output-dir>/archaeology.json`.

## Contract highlights

- Deterministic ordering of rules.
- Explicit overwrite gate via force.
- Privacy gate keeps data out.
- Bounded analysis limits max commits.
- Noise filtering ignores glob matches.
- Path classes tag folders precisely.
- Coupling classes show risk securely.
- Confidence explainers boost trust metrics.

## Verify

After a successful run you should see:

- `artifacts/archaeology.json`.
- `artifacts/archaeology_report.md`.
- (optional) `artifacts/archaeology_share.md`.

## Local validation

```bash
npm test
npm run test:deep
npm run docs:lint
```

## Troubleshooting

- **`error: Not a git repo: ...`**: pass a path that contains a `.git/` directory.
- **`Refusing overwrite: ... (use --force)`**: add `--force` when re-running into the same `--output-dir`.
- **`error: --include-authors requires --ack-pii`**: add `--ack-pii` to opt into metadata checks.
- **`error: git not found`**: install `git` locally and ensure it is on your `PATH`.

## Competition-led build process

See `docs/competition-matrix.md`.

## Contributing / security

- Contributing guide: `CONTRIBUTING.md`.
- Security policy: `SECURITY.md`.
- Code of conduct: `CODE_OF_CONDUCT.md`.

## Project info

- Maintainer: @jscraik.
- Last updated: 2026-02-15.
- License: Apache-2.0.
