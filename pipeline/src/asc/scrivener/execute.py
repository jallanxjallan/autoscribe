"""Scrivener execution boundary for key-only inbox entries."""

from __future__ import annotations

from dataclasses import dataclass

from asc.ledger.write import table_for_key, write_key


@dataclass(frozen=True, slots=True)
class ScrivenerExecutionReport:
    artifact_key: str
    kind: str
    table: str


class ScrivenerExecutor:
    def execute(self, artifact_key: str) -> ScrivenerExecutionReport:
        key = _required_text(artifact_key, "scrivener artifact key")
        table = table_for_key(key)
        kind = write_key(key)
        return ScrivenerExecutionReport(artifact_key=key, kind=kind, table=table)


def _required_text(value: object, field: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field} must be non-empty")
    return text


__all__ = ["ScrivenerExecutionReport", "ScrivenerExecutor"]
