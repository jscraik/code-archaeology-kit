# Contradictions and cleanup

## Contradictions found

1. Global `/Users/jamiecraik/.codex/AGENTS.md` describes a configuration-only repo, while this repository is a Python CLI project.
   - Question: Keep local repo instructions as the canonical source for package manager and validation commands?
2. Frontend website guidance exists, but this repository has no primary frontend framework files (`vite.config.*`, `next.config.*`, `src/main.*`) as default development targets.
   - Resolved on 2026-02-24: keep frontend rules as conditional policy only.
3. README install examples use `python -m pip`, while this repo guide standardizes on `python3 -m pip`.
   - Question: Should we normalize all docs to `python3` for consistency?

## Flag for deletion

- Any stale claim that `rg` or `fd` is unavailable in this environment.
- Duplicated global protocol text copied into repo docs instead of linked references.
- Unconditional frontend workflow requirements in non-frontend tasks.
