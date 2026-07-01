from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CheckStatus(Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    INFO = "INFO"


@dataclass(frozen=True)
class Check:
    status: CheckStatus
    message: str


@dataclass
class CheckReport:
    checks: list[Check] = field(default_factory=list)

    def add(self, status: CheckStatus, message: str) -> None:
        self.checks.append(Check(status, message))

    def passed(self, message: str) -> None:
        self.add(CheckStatus.PASS, message)

    def warning(self, message: str) -> None:
        self.add(CheckStatus.WARN, message)

    def failed(self, message: str) -> None:
        self.add(CheckStatus.FAIL, message)

    def info(self, message: str) -> None:
        self.add(CheckStatus.INFO, message)

    @property
    def failures(self) -> int:
        return sum(check.status is CheckStatus.FAIL for check in self.checks)

    @property
    def warnings(self) -> int:
        return sum(check.status is CheckStatus.WARN for check in self.checks)

    def print(self) -> None:
        for check in self.checks:
            print(f"[{check.status.value}] {check.message}")
        print(f"[SUMMARY] failures={self.failures} warnings={self.warnings}")

