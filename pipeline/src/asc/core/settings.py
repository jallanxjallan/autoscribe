from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Config:
    ledger_path: Path
    redis_url: str
    log_level: str
    step_results_ttl_seconds: int


@lru_cache(maxsize=1)
def get_config() -> Config:
    return Config(
        ledger_path=Path("~/.local/share/autoscribe/db/ledger.sql").expanduser(),
        redis_url="redis://localhost:6379/0",
        log_level="INFO",
        step_results_ttl_seconds=86400,
    )


__all__ = [
    "Config",
    "get_config",
]