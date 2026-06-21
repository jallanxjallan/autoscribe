"""Shared task helpers for orchestrator task factories."""

from __future__ import annotations

from typing import Any


def task_key(task: Any) -> str:
    return str(task.key)


__all__ = ["task_key"]
