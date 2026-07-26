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

    records: list[dict[str, Any]] = []
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


def _decode_object(value: Any, *, slug: str, field: str) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ObsError(f"{slug}: stored {field} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ObsError(f"{slug}: stored {field} must decode to an object")
    return value


def _materialize_plan(record: dict[str, Any]) -> dict[str, Any]:
    """Expose a stored plan definition in the shape used by Define Plan.

    The upload envelope is not persisted. A full plan read must therefore
    return artifact fields such as ``metadata_json`` and ``steps_json`` (or an
    already materialized ``payload`` object). Catalog-only records cannot be
    used to edit an existing plan.
    """
    slug = str(record.get("slug") or record.get("record_identity") or "<unknown>")

    raw_payload = record.get("payload")
    if raw_payload is not None:
        payload = _decode_object(raw_payload, slug=slug, field="payload")
        return {**record, **payload}

    if "steps" in record and isinstance(record.get("steps"), dict):
        return dict(record)

    if "steps_json" not in record:
        raise ObsError(
            f"{slug}: control returned catalog metadata only; "
            "a full plan-read operation must return metadata_json and steps_json"
        )

    steps = _decode_object(record.get("steps_json"), slug=slug, field="steps_json")
    metadata = _decode_object(record.get("metadata_json", "{}"), slug=slug, field="metadata_json")

    result = {
        **record,
        **metadata,
        "record_type": "plan",
        "record_identity": slug,
        "slug": slug,
        "steps": steps,
    }
    result.pop("metadata_json", None)
    result.pop("steps_json", None)
    return result


def load_plan(slug: str) -> dict[str, Any]:
    slug = slug.strip()
    if not slug:
        raise ObsError("plan.load requires slug")
    for record in list_plans():
        if record["slug"] == slug:
            return _materialize_plan(record)
    raise ObsError(f"plan not found in pipeline: {slug}")


def _plan_payload(record: dict[str, Any], *, slug: str) -> dict[str, Any]:
    payload = record.get("payload")
    if not isinstance(payload, dict):
        raise ObsError(f"{slug}: plan.save requires payload object")
    return dict(payload)


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

    content = _plan_payload(record, slug=slug)
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
        raise ObsError(f"{slug}: plan step indexes must be contiguous from 1; got {actual}")

    for ordinal, (_, step) in enumerate(ordered, 1):
        if not isinstance(step, dict):
            raise ObsError(f"{slug}: step {ordinal} must be an object")
        refs = step.get("instruction_slugs", {})
        if refs is None:
            refs = {}
        if not isinstance(refs, dict):
            raise ObsError(f"{slug}: step {ordinal} instruction_slugs must be an object")
        for label in ("role", "context", "specifics", "instructions"):
            value = refs.get(label, [])
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ObsError(
                    f"{slug}: step {ordinal} instruction_slugs.{label} must be a slug list"
                )

    instruction_results = sync_instructions(cwd, instruction_sets or [])

    envelope = {
        "record_type": "plan",
        "record_identity": slug,
        "payload": content,
    }
    line = json.dumps(envelope, ensure_ascii=False) + "\n"
    result = run(
        [autoscribe_bin(), "upload", "plans"],
        cwd=cwd,
        input_text=line,
    )
    return {
        "record": envelope,
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


def sync_plan(record: dict[str, Any], *, cwd: Path) -> dict[str, Any]:
    """Reconcile a vault-local plan and its instruction sources with the server."""
    slug = str(record.get("record_identity") or record.get("slug") or "").strip()
    if not slug:
        raise ObsError("dispatch plan record missing record_identity")
    payload = record.get("payload")
    if not isinstance(payload, dict):
        raise ObsError(f"{slug}: local plan payload must be an object")

    instruction_sets = ((record.get("local") or {}).get("instruction_sets") or [])
    if not isinstance(instruction_sets, list):
        raise ObsError(f"{slug}: local instruction_sets must be a list")
    instruction_results = sync_instructions(cwd, instruction_sets)

    local_canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    remote_payload = None
    for candidate in list_plans():
        if candidate["slug"] == slug:
            try:
                remote_payload = _materialize_plan(candidate).get("payload")
                if remote_payload is None:
                    remote_payload = {
                        "label": candidate.get("label", ""),
                        "description": candidate.get("description", ""),
                        "steps": candidate.get("steps", {}),
                    }
            except ObsError:
                remote_payload = None
            break
    if isinstance(remote_payload, dict):
        remote_canonical = json.dumps(remote_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if remote_canonical == local_canonical:
            return {"slug": slug, "status": "current", "uploaded": False, "instructions": instruction_results}

    envelope = {"record_type": "plan", "record_identity": slug, "payload": payload}
    result = run([autoscribe_bin(), "upload", "plans"], cwd=cwd,
                 input_text=json.dumps(envelope, ensure_ascii=False) + "\n")
    return {
        "slug": slug,
        "status": "uploaded",
        "uploaded": True,
        "instructions": instruction_results,
        "pipeline_output": result.stdout.strip(),
    }
