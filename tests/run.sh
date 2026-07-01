#!/usr/bin/env bash

set -eu

ROOT="$(cd -- "${0%/*}/.." && pwd -P)"
PYTHON_BIN="${ELK_TEST_PYTHON:-python3.13}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  printf '[FAIL] test interpreter not found: %s\n' "$PYTHON_BIN" >&2
  exit 1
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
"$PYTHON_BIN" -m compileall -q "$ROOT/src" "$ROOT/tests"
"$PYTHON_BIN" -m unittest discover -s "$ROOT/tests" -p 'test_*.py' -v
printf 'All focused POC tests passed.\n'
