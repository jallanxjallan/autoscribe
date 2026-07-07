from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from asc.core.config import config


@dataclass(frozen=True)
class Settings:
    ledger_path: Path
    redis_url: str
    log_level: str = "INFO"
    step_results_ttl_seconds: int = 86400


# Backward-compatible alias for older imports.
Config = Settings


@lru_cache(maxsize=1)
def get_config() -> Settings:
    return Settings(
        ledger_path=config.sql_ledger_path,
        redis_url=config.redis_url,
    )


__all__ = ["Config", "Settings", "get_config"]
