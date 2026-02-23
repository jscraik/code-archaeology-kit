# Contradictions and cleanup

## Contradictions found
1. Global guidance from `/Users/jamiecraik/.codex/AGENTS.md` lists package manager as **none (configuration-only repo)**, but this repository uses `python3 -m pip` and has `package.json` scripts.
   - Which instruction wins for tooling commands?
2. Required global protocol references mention agent-first scaffold docs (`agent-first-scaffold-spec`, `README.checklist`, `validator-contracts`, `strict-toggle-governance`), but those files are not all present.
   - Should missing files block scaffold-only instructions, or should we proceed with fallback references only?
3. This repository is confirmed for GitHub Pages (`https://jscraik.github.io/unfinished-cemetery/`) while it still has no local Pages source files in repo evidence.
   - Keep frontend policy active for web-facing tasks, but treat local-server commands as pending until verified by task scope.

## Flag for deletion
- Remove any legacy assumption that `pytest`/`npm` are always available; keep checks environment-aware.
- Remove any duplicated global protocol content copied into repo files; keep only links.
- Merge `Frontend website rules` into a dedicated docs file and keep root `AGENTS.md` concise.
