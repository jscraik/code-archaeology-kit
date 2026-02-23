# AGENTS.md

schema_version: 1

## One-sentence project description
Code Archaeology Kit is a standalone Python CLI that scans git history and emits actionable archaeology artifacts.

## References (informational)
- Global protocol: `/Users/jamiecraik/.codex/instructions/rvcp-common.md`
- Security and standards baseline: `/Users/jamiecraik/.codex/instructions/standards.md`
- Local memory workflow: `/Users/jamiecraik/.codex/instructions/local-memory.md` (if using local-memory MCP)
- Not observed on disk: `/Users/jamiecraik/.codex/instructions/agent-first-scaffold-spec.md` (missing when checked)

## Tooling essentials
- Package manager: Python packages via `python3 -m pip` (install entrypoint with `python3 -m pip install -e .`).
- `npm` is optional for markdown lint scripts only when available (`npm run docs:lint`).
- Package manager compatibility posture: canonical-only.

## Non-standard build/typecheck commands
- Build/install command: `python3 -m pip install -e .`
- CLI entrypoint check: `cak scan --help`
- Test command (project standard): `python3 -m pytest -q`
- Documentation check: `python3 scripts/check_readability.py README.md`
- No dedicated static typecheck command is configured in this repo.

## Tooling policy
- Before using code search at repo scale, prefer `rg` and `fd`.
- In this environment, `rg` and `fd` are missing and this fact must be called out before attempting repo-wide searches.
- Use `python3` for command execution and parsing where possible.

## Global instruction discovery order
1. `/Users/jamiecraik/.codex/AGENTS.md`
2. This root `AGENTS.md`
3. `docs/agents/*.md` linked below
4. Ask for conflict resolution before merging contradictory instructions.

## Table of contents
- [Instruction map](docs/agents/01-instruction-map.md)
- [Tooling policy](docs/agents/02-tooling-policy.md)
- [Local memory workflow](docs/agents/03-local-memory.md)
- [Validation and checks](docs/agents/04-validation.md)
- [Contradictions and cleanup](docs/agents/05-contradictions-and-cleanup.md)
- [Frontend website rules for GitHub Pages](docs/agents/06-frontend-website-rules.md)

## Frontend website rules
Active for this repo because user confirmed it is a GitHub Pages target.
See: `docs/agents/06-frontend-website-rules.md`
