from __future__ import annotations


class ElkctlError(RuntimeError):
    """Base exception for an expected, operator-actionable failure."""


class ConfigurationError(ElkctlError):
    """The site configuration is missing or invalid."""


class CommandError(ElkctlError):
    """An external command failed."""

    def __init__(self, executable: str, returncode: int, detail: str = "") -> None:
        message = f"{executable} failed with exit code {returncode}"
        if detail:
            message = f"{message}: {detail.strip()}"
        super().__init__(message)
        self.executable = executable
        self.returncode = returncode


class PreflightError(ElkctlError):
    """One or more mandatory preflight checks failed."""

