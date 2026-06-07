from __future__ import annotations

from typing import Any

__all__ = [
    "scrivener_daemon_status",
    "start_scrivener_daemon",
    "stop_scrivener_daemon",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from asc.ledger.lifecycle import (  # noqa: PLC0415
            scrivener_daemon_status,
            start_scrivener_daemon,
            stop_scrivener_daemon,
        )

        return {
            "scrivener_daemon_status": scrivener_daemon_status,
            "start_scrivener_daemon": start_scrivener_daemon,
            "stop_scrivener_daemon": stop_scrivener_daemon,
        }[name]

    raise AttributeError(name)
