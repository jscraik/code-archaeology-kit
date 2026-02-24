# Tooling policy

## Tooling essentials

- Core language tool: `python3`
- Preferred install: `python3 -m pip install -e .`
- Install fallback for older pip: `python3 -m pip install .`
- CLI verification entrypoint: `PYTHONPATH=src python3 -m code_archaeology scan --help`
- Shell wrapper for commands: `zsh -lc`

## Tool availability checks

Run before repo-wide search or JSON parsing:

- `command -v rg`
- `command -v fd`
- `command -v jq`
- `command -v python3`
- `command -v npm`

Observed in this environment on 2026-02-24:

- `rg`, `fd`, `jq`, `python3`, and `npm` are available.

## Command conventions

- Prefer `rg`, `fd`, and `jq` over `grep`, `find`, and regex parsing.
- Use repository commands already documented in `README.md`, `pyproject.toml`, and `package.json`.
- Do not introduce new dependency managers.
