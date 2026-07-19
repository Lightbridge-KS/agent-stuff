"""Stable, agent-correctable errors for packaged notebook operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class NotebookToolError(Exception):
    """An expected failure with a stable branchable code and recovery hint."""

    code: str
    message: str
    recovery: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "recovery": self.recovery,
        }
        if self.details:
            payload["details"] = self.details
        return payload


def invalid_operation(message: str, recovery: str) -> NotebookToolError:
    return NotebookToolError("INVALID_OPERATION", message, recovery)
