#!/usr/bin/env bash
# Linux/macOS wrapper. All the work is in build_wheel.py so that every
# platform runs the same code path and the two wrappers cannot drift.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Try candidates in order and take the first that is genuinely >= 3.11,
# rather than trusting the name. `python3` is not always a Python: under
# Git Bash on Windows it resolves to the Microsoft Store stub, which
# answers every invocation without being an interpreter at all.
py=""
candidates=()
[[ -n "${VIRTUAL_ENV:-}" ]] && candidates+=("${VIRTUAL_ENV}/bin/python")
candidates+=(python3 python)
for candidate in "${candidates[@]}"; do
  command -v "$candidate" >/dev/null 2>&1 || continue
  if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    py="$candidate"
    break
  fi
done

if [[ -z "$py" ]]; then
  echo "error: no Python >= 3.11 found (tried: ${candidates[*]})" >&2
  echo "hint: activate a venv, or install a newer Python" >&2
  exit 1
fi

# Not optional: this project's sources and fixtures are full of Korean,
# and a child Python still defaults to the ANSI code page on Windows.
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

exec "$py" "$here/build_wheel.py" "$@"
