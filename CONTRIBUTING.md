# Contributing

Thanks for your interest in improving Code Archaeology Kit.

## When to use

Use this guide when you want to make a code or documentation change and open a PR.

## Inputs

- Python: 3.11+
- Git: installed (the CLI shells out to `git`)

## Outputs

- A PR with tests passing (`pytest -q`)

## Development setup

```bash
git clone <YOUR_FORK_URL>
cd code-archaeology-kit
python -m pip install -e .
```

## Run tests

```bash
pytest -q
```

## Try the CLI locally (no install)

```bash
PYTHONPATH=src python -m code_archaeology scan --help
```

## Before you open a PR

- [ ] `pytest -q` passes
- [ ] Any new CLI flags are documented in `README.md`
- [ ] Outputs remain privacy-safe by default (no repo path, no commit messages, no authors unless explicitly enabled)
