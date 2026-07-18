from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .catalog import pipeline_snapshot
from .errors import ObsError
from .process import run
from .executables import autoscribe_bin
from .instruction_upload import sync_instructions


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


def save_plan(
    record: dict[str, Any],
    *,
    cwd: Path,
    instruction_sets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Synchronize referenced instructions, then upload the plan last."""
    slug = str(record.get("record_identity") or record.get("slug") or "").strip()
    if not slug:
        raise ObsError("plan record missing record_identity")

    raw_content = record.get("record_content")
    if isinstance(raw_content, str):
        try:
            content = json.loads(raw_content)
        except json.JSONDecodeError as exc:
            raise ObsError(f"{slug}: record_content is not valid JSON: {exc}") from exc
    else:
        content = raw_content

    if not isinstance(content, dict):
        raise ObsError(f"{slug}: plan record_content must be an object")

    raw_steps = content.get("steps")
    if not isinstance(raw_steps, dict) or not raw_steps:
        raise ObsError(f"{slug}: plan steps must be a non-empty indexed object")

    def step_order(item: tuple[Any, Any]) -> int:
        key, _ = item
        text = str(key)
        if not text.isdigit() or int(text) < 1:
            raise ObsError(f"{slug}: invalid plan step index: {key!r}")
        return int(text)

    ordered = sorted(raw_steps.items(), key=step_order)
    expected = list(range(1, len(ordered) + 1))
    actual = [int(str(key)) for key, _ in ordered]
    if actual != expected:
        raise ObsError(
            f"{slug}: plan step indexes must be contiguous from 1; got {actual}"
        )

    for ordinal, (_, step) in enumerate(ordered, 1):
        if not isinstance(step, dict):
            raise ObsError(f"{slug}: step {ordinal} must be an object")
        refs = step.get("instruction_slugs", {})
        if refs is None:
            refs = {}
        if not isinstance(refs, dict):
            raise ObsError(f"{slug}: step {ordinal} instruction_slugs must be an object")
        for label in ("role", "context", "instructions"):
            value = refs.get(label)
            if value is not None and not isinstance(value, str):
                raise ObsError(
                    f"{slug}: step {ordinal} instruction_slugs.{label} must be a slug string"
                )

    # This transaction must complete before the plan becomes visible.
    instruction_results = sync_instructions(cwd, instruction_sets or [])

    payload = {
        "record_type": "plan",
        "record_identity": slug,
        "record_content": json.dumps(content, ensure_ascii=False),
    }
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    result = run(
        [autoscribe_bin(), "upload", "plans"],
        cwd=cwd,
        input_text=line,
    )
    return {
        "record": payload,
        "instructions": instruction_results,
        "pipeline_output": result.stdout.strip(),
    }


def delete_plan(slug: str, *, cwd: Path) -> dict[str, Any]:
    command = os.environ.get("AUTOSCRIBE_DELETE_PLAN_COMMAND")
    if not command:
        raise ObsError("plan deletion is not configured; set AUTOSCRIBE_DELETE_PLAN_COMMAND")
    args = [part.format(slug=slug) for part in command.split()]
    result = run(args, cwd=cwd)
    return {"slug": slug, "pipeline_output": result.stdout.strip()}
