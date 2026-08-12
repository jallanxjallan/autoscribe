from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .errors import ObsError


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObsError(f"could not read JSON manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ObsError(f"manifest must contain a JSON object: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = dict(value)
    clean.pop("filepath", None)
    clean["updated"] = now_iso()
    path.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    for key in (
        "calls", "prompt_plan_pairs", "promptPlanPairs", "slug_pairs", "pairs",
        "items", "records", "dispatch",
    ):
        value = manifest.get(key)
        if isinstance(value, list):
            return value
    raise ObsError("run manifest must contain a calls or prompt_plan_pairs array")
