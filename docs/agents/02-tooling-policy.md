# Tooling policy

## Tooling essentials
- Core language tool: `python3`
- Project install: `python3 -m pip install -e .`
- CLI entrypoint for verification: `cak scan --help`

## Tool availability checks
- Confirm command availability before use:
  - `command -v python3`
  - `command -v rg`
  - `command -v fd`
  - `command -v jq`
- In this environment, `rg` and `fd` are missing.

## Command conventions
- Use repo-local file paths and commands shown in repository files.
- Do not introduce new dependency managers.
- Prefer concise commands that produce deterministic output for checklists.
