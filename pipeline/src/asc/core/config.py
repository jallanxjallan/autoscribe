from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


REDIS_URL = "redis://127.0.0.1:6379/0"
SQL_LEDGER_PATH = Path("/home/jeremy/.local/share/autoscribe/db/ledger.sql")

# External runtime components live outside the AutoScribe source tree.
# This root must be the parent of engines/ and scripts/.
AUTOSCRIBE_EXTENSIONS_ROOT = Path("/home/jeremy/AutoScribe/extensions").resolve()

# Current live extension package names.
AUTOSCRIBE_ENGINE_PACKAGES = ("engines",)
AUTOSCRIBE_SCRIPT_PACKAGES = ("scripts",)


def ensure_runtime_paths() -> None:
    """Make configured runtime extension roots importable once per process."""

    if not AUTOSCRIBE_EXTENSIONS_ROOT.is_dir():
        raise FileNotFoundError(
            f"AutoScribe extensions root not found: {AUTOSCRIBE_EXTENSIONS_ROOT}"
        )

    root = str(AUTOSCRIBE_EXTENSIONS_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


@dataclass(frozen=True)
class Config:
    redis_url: str = REDIS_URL
    sql_ledger_path: Path = SQL_LEDGER_PATH


config = Config()


__all__ = [
    "AUTOSCRIBE_ENGINE_PACKAGES",
    "AUTOSCRIBE_EXTENSIONS_ROOT",
    "AUTOSCRIBE_SCRIPT_PACKAGES",
    "Config",
    "REDIS_URL",
    "SQL_LEDGER_PATH",
    "config",
    "ensure_runtime_paths",
]