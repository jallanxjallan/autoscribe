"""Non-secret runtime configuration for AutoScribe.

These values are source-controlled installation configuration. Paths outside
this source tree are runtime targets/resources, never exterior configuration
files.
"""

from __future__ import annotations

from pathlib import Path


REDIS_URL = "redis://127.0.0.1:6379/0"
SQL_LEDGER_PATH = Path("/home/jeremy/.local/share/autoscribe/db/ledger.sql")
EXTENSIONS_ROOT = Path("/home/jeremy/Work/Extensions")
ENGINE_PACKAGES = ("engines",)
SCRIPT_PACKAGES = ("scripts",)
INSTRUCTION_TTL_SECONDS = 60 * 60 * 24 * 3
MIN_REMAINING_INSTRUCTION_TTL_SECONDS = 60 * 60 * 24
RESPONSE_TTL_SECONDS = 60 * 60 * 24 * 7
FAILURE_TTL_SECONDS = 60 * 60 * 24 * 7


__all__ = [
    "ENGINE_PACKAGES",
    "EXTENSIONS_ROOT",
    "FAILURE_TTL_SECONDS",
    "INSTRUCTION_TTL_SECONDS",
    "MIN_REMAINING_INSTRUCTION_TTL_SECONDS",
    "REDIS_URL",
    "RESPONSE_TTL_SECONDS",
    "SCRIPT_PACKAGES",
    "SQL_LEDGER_PATH",
]
