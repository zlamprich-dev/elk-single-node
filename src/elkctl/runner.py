from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
from typing import Mapping, Sequence

from .errors import CommandError


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    """Run host commands without invoking a shell or logging secret arguments."""

    def __init__(self, *, verbose: bool = False) -> None:
        self.verbose = verbose

    def run(
        self,
        arguments: Sequence[str | Path],
        *,
        check: bool = True,
        env: Mapping[str, str] | None = None,
        input_text: str | None = None,
        timeout: int = 120,
    ) -> CommandResult:
        args = [str(value) for value in arguments]
        if self.verbose:
            # Arguments can contain credentials. Show only the executable.
            print(f"[elkctl] running: {Path(args[0]).name}", file=sys.stderr)
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        try:
            completed = subprocess.run(
                args,
                input=input_text,
                text=True,
                capture_output=True,
                env=process_env,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandError(
                Path(args[0]).name, 124, f"timed out after {timeout} seconds"
            ) from exc
        result = CommandResult(completed.returncode, completed.stdout, completed.stderr)
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise CommandError(Path(args[0]).name, result.returncode, detail)
        return result
