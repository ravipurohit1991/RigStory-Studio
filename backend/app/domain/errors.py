"""Structured validation issues with actionable error codes."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One invariant violation, addressable by code and document path."""

    code: str
    message: str
    path: str = ""

    def __str__(self) -> str:
        location = f" at {self.path}" if self.path else ""
        return f"{self.code}{location}: {self.message}"


@dataclass(frozen=True)
class DomainValidationError(Exception):
    """Raised when a document violates domain invariants."""

    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        return "; ".join(str(issue) for issue in self.issues) or "domain validation failed"


def raise_if_issues(issues: list[ValidationIssue]) -> None:
    if issues:
        raise DomainValidationError(tuple(issues))
