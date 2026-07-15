from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .catalog import pipeline_snapshot
from .errors import ObsError
from .process import run


def _asc_bin() -> str:
    return os.environ.get("AUTOSCRIBE_BIN") or os.environ.get("ASC_BIN") or "asc"


def _plan_values(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    registries = snapshot.get("registries") if isinstance(snapshot, dict) else None
    values: list[Any] = []
    if isinstance(registries, dict):
        for name in ("plans", "plan"):
            current = registries.get(name)
            if isinstance(current, dict):
                values.extend(current.values())
            elif isinstance(current, list):
                values.extend(current)
    if not values and isinstance(snapshot.get("plans"), list):
        values.extend(snapshot["plans"])
    records = []
    for value in values:
        if not isinstance(value, dict):
            continue
        slug = str(value.get("record_identity") or value.get("slug") or "").strip()
        if not slug:
            continue
        records.append({**value, "record_identity": slug, "slug": slug, "record_type": "plan"})
    return records


def list_plans() -> list[dict[str, Any]]:
    records = _plan_values(pipeline_snapshot("control"))
    return sorted(records, key=lambda item: str(item.get("label") or item["slug"]).lower())


def load_plan(slug: str) -> dict[str, Any]:
    for record in list_plans():
        if record["slug"] == slug:
            return record
    raise ObsError(f"plan not found in pipeline: {slug}")


def save_plan(record: dict[str, Any], *, cwd: Path) -> dict[str, Any]:
    slug = str(record.get("record_identity") or record.get("slug") or "").strip()
    if not slug:
        raise ObsError("plan record missing record_identity")
    steps = record.get("steps")
    if not isinstance(steps, (dict, list)) or not steps:
        raise ObsError(f"{slug}: plan has no executable steps")
    payload = {**record, "record_type": "plan", "record_identity": slug, "slug": slug}
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    result = run([_asc_bin(), "upload", "plans"], cwd=cwd, input_text=line)
    return {"record": payload, "pipeline_output": result.stdout.strip()}


def delete_plan(slug: str, *, cwd: Path) -> dict[str, Any]:
    command = os.environ.get("AUTOSCRIBE_DELETE_PLAN_COMMAND")
    if not command:
        raise ObsError("plan deletion is not configured; set AUTOSCRIBE_DELETE_PLAN_COMMAND")
    args = [part.format(slug=slug) for part in command.split()]
    result = run(args, cwd=cwd)
    return {"slug": slug, "pipeline_output": result.stdout.strip()}
