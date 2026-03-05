#!/usr/bin/env bash
set -euo pipefail

abs_python_path() {
  local candidate="$1"
  local dir
  dir="$(cd "$(dirname "$candidate")" && pwd -P)"
  echo "$dir/$(basename "$candidate")"
}

resolve_python() {
  if [[ -x .venv/bin/python ]]; then
    abs_python_path .venv/bin/python
    return
  fi
  if [[ -x ../.venv/bin/python ]]; then
    abs_python_path ../.venv/bin/python
    return
  fi
  if [[ -x ../../.venv/bin/python ]]; then
    abs_python_path ../../.venv/bin/python
    return
  fi
  if command -v uv >/dev/null 2>&1 && [[ -f uv.lock ]]; then
    echo "uv"
    return
  fi
  echo "python3"
}

runner="$(resolve_python)"
if [[ "$runner" == "uv" ]]; then
  if [[ -d src ]]; then
    PYTHONPATH=src uv run pytest "$@"
  else
    uv run pytest "$@"
  fi
  exit 0
fi

if [[ "$runner" == "python3" ]] && ! python3 -c 'import pytest' >/dev/null 2>&1; then
  cat >&2 <<'EOF'
[run-pytest] pytest is not available in python3.
Install test deps first: python3 -m pip install -e ".[dev]"
Or use a project venv at .venv/bin/python.
EOF
  exit 1
fi

if [[ -d src ]]; then
  PYTHONPATH=src "$runner" -m pytest "$@"
else
  "$runner" -m pytest "$@"
fi
