"""Non-secret runtime configuration for AutoScribe.

These values are source-controlled installation configuration. Paths outside
this source tree are runtime targets/resources, never exterior configuration
files.
"""

from __future__ import annotations

from pathlib import Path


REDIS_URL = "redis://127.0.0.1:6379/0"
SQL_LEDGER_PATH = Path("/home/jeremy/.local/share/autoscribe/db/ledger.sql")
EXTENSIONS_ROOT = Path("/home/jeremy/.local/share/autoscribe/cache/control")
ENGINE_PACKAGES = ("engines",)
SCRIPT_PACKAGES = ("scripts",)


__all__ = [
    "ENGINE_PACKAGES",
    "EXTENSIONS_ROOT",
    "REDIS_URL",
    "SCRIPT_PACKAGES",
    "SQL_LEDGER_PATH",
]
