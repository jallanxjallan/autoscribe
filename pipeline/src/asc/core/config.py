from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REDIS_URL = "redis://127.0.0.1:6379/0"
SQL_LEDGER_PATH = Path("/home/jeremy/.local/share/autoscribe/db/ledger.sql")
# External runtime components live outside the AutoScribe source tree.
# Keep this deliberately hard-coded for the local development workflow.
AUTOSCRIBE_EXTENSIONS_ROOT = Path("/home/jeremy/AutoScribe/extensions").resolve()

AUTOSCRIBE_ENGINE_PACKAGES = ("engines",)
AUTOSCRIBE_SCRIPT_PACKAGES = ("scripts",)





@dataclass(frozen=True)
class Config:
    redis_url: str = REDIS_URL
    sql_ledger_path: Path = SQL_LEDGER_PATH


config = Config()