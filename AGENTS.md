# AGENTS.md

schema_version: 1

## One-sentence project description

Code Archaeology Kit is a standalone Python CLI that scans git history and emits actionable archaeology artifacts.

## Mandatory workflow snippet

1. Explore project first, then invoke skill.
2. IMPORTANT: Prefer retrieval-led reasoning over pre-training-led reasoning for any React, Tauri, Apps-SDK-ui, Tailwind, Vite, Storybook + Chat Widget tasks.
3. Add a Table of Contents for docs.

## References (informational)

- Global protocol: `/Users/jamiecraik/.codex/instructions/rvcp-common.md`
- Security and standards baseline: `/Users/jamiecraik/.codex/instructions/standards.md`
- Local memory workflow: `/Users/jamiecraik/.codex/instructions/local-memory.md` (if using local-memory MCP)
- Not observed on disk: `/Users/jamiecraik/.codex/instructions/agent-first-scaffold-spec.md`

## Required essentials

- Package manager: Python packages via `python3 -m pip`.
- Optional docs tooling: `npm` scripts from `package.json`.
- Default compatibility posture: canonical-only.

## Tooling essentials

- Run shell commands with `zsh -lc`.
- Prefer `rg`, `fd`, and `jq`; verify availability with `command -v` when needed.
- Before choosing tools, read `/Users/jamiecraik/.codex/instructions/tooling.md`.
- Execution mode is single-threaded unless the user explicitly asks to parallelize.

## Non-standard build/typecheck commands

- Install with test deps: `python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"`
- Install fallback (older pip): `.venv/bin/python -m pip install ".[dev]"`
- CLI check (run-from-source): `PYTHONPATH=src python3 -m code_archaeology scan --help`
- Tests: `npm test` (prefers `.venv/bin/python`, falls back to `python3`)
- Deep tests/artifacts: `npm run test:deep`
- Docs readability: `python3 scripts/check_readability.py README.md`
- No dedicated static typecheck command is configured.

## Global instruction discovery order

1. `/Users/jamiecraik/.codex/AGENTS.md`
2. This root `AGENTS.md`
3. `docs/agents/*.md` linked below
4. If instructions conflict, pause and ask which one wins

## Table of Contents

- [Instruction map](docs/agents/01-instruction-map.md)
- [Tooling policy](docs/agents/02-tooling-policy.md)
- [Local memory workflow](docs/agents/03-local-memory.md)
- [Validation and checks](docs/agents/04-validation.md)
- [Contradictions and cleanup](docs/agents/05-contradictions-and-cleanup.md)
- [Frontend website rules](docs/agents/06-frontend-website-rules.md)
- [Flaky Test Artifact Capture](#flaky-test-artifact-capture)

## Notes

- Keep root guidance minimal; put detailed procedures in `docs/agents/`.
- Use frontend website rules only for frontend or GitHub Pages tasks.

## Flaky Test Artifact Capture

- Run `bash scripts/test-with-artifacts.sh all` (or `pnpm run test:artifacts` / `npm run test:artifacts` / `bun run test:artifacts`) to emit machine-readable flaky evidence under `artifacts/test`.
- Optional targeted modes:
  - `bash scripts/test-with-artifacts.sh unit`
  - `bash scripts/test-with-artifacts.sh integration`
  - `bash scripts/test-with-artifacts.sh e2e`
- Commit/retain stable artifact paths for local automation ingestion:
  - `artifacts/test/summary-*.json`
  - `artifacts/test/test-output-*.log`
  - `artifacts/test/junit-*.xml` (when supported by test runner)
  - `artifacts/test/*-results.json` (when supported by test runner)
  - `artifacts/test/artifact-manifest.json`
- Keep artifact filenames stable (no timestamps in filenames) so recurring flake scans can compare runs.
