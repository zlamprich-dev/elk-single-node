from __future__ import annotations

import sys


def log(message: str) -> None:
    print(f"[elkctl] {message}", file=sys.stderr)


def warning(message: str) -> None:
    print(f"[elkctl] WARNING: {message}", file=sys.stderr)


def error(message: str) -> None:
    print(f"[elkctl] ERROR: {message}", file=sys.stderr)

