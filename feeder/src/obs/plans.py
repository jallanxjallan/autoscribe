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
from .contracts import upload_record


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

    envelope = upload_record(type="plan", identity=slug, content=content, extra={})
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





def _plan_path(cwd: Path, slug: str) -> Path:
    plan_slug = str(slug or "").strip()
    if not plan_slug:
        raise ObsError("dispatch requires plan_slug")
    if not plan_slug.startswith("plan.") or any(ch in plan_slug for ch in "/\\"):
        raise ObsError(f"invalid plan slug: {plan_slug}")
    path = (cwd / "_plans" / f"{plan_slug}.json").resolve()
    try:
        path.relative_to(cwd.resolve())
    except ValueError as exc:
        raise ObsError(f"plan path escaped active vault: {path}") from exc
    return path


def _rg_slug_paths(cwd: Path, slug: str) -> list[Path]:
    """Find Markdown instruction files whose frontmatter contains the exact slug."""
    result = run(
        ["rg", "-l", "--glob", "*.md", "--", rf"^slug:\s*{slug.replace('.', r'\.') }\s*$", "."],
        cwd=cwd,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise ObsError(f"rg failed while resolving {slug}: {result.stderr.strip()}")
    return [(cwd / line.strip()).resolve() for line in result.stdout.splitlines() if line.strip()]


def _single_slug_path(cwd: Path, slug: str, *, label: str) -> Path:
    matches = _rg_slug_paths(cwd, slug)
    if not matches:
        raise ObsError(f"{label} slug not found in vault: {slug}")
    if len(matches) > 1:
        rendered = ", ".join(path.relative_to(cwd.resolve()).as_posix() for path in matches)
        raise ObsError(f"duplicate {label} slug {slug}: {rendered}")
    return matches[0]


def load_local_plan(cwd: Path, slug: str) -> dict[str, Any]:
    """Load _plans/<slug>.json directly; plans do not require ripgrep."""
    plan_slug = str(slug or "").strip()
    path = _plan_path(cwd, plan_slug)
    if not path.is_file():
        raise ObsError(f"plan not found: {path.relative_to(cwd.resolve()).as_posix()}")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ObsError(f"{path}: invalid JSON plan: {exc}") from exc
    if not isinstance(record, dict):
        raise ObsError(f"{path}: plan JSON must be an object")
    actual = str(record.get("record_identity") or record.get("slug") or "").strip()
    if actual != plan_slug:
        raise ObsError(f"{path}: expected plan slug {plan_slug}, found {actual or '<empty>'}")
    return {
        **record,
        "record_type": "plan",
        "record_identity": plan_slug,
        "slug": plan_slug,
        "path": path.relative_to(cwd.resolve()).as_posix(),
    }


def _sync_payload(record: dict[str, Any], *, slug: str) -> dict[str, Any]:
    payload = record.get("payload")
    if not isinstance(payload, dict):
        raise ObsError(f"{slug}: local plan must contain payload")
    steps = payload.get("steps")
    if not isinstance(steps, dict) or not steps:
        raise ObsError(f"{slug}: local plan payload must contain non-empty steps")
    return dict(payload)


def _instruction_slugs(payload: dict[str, Any], *, plan_slug: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    steps = payload.get("steps") or {}
    for step_number, step in steps.items():
        if not isinstance(step, dict):
            raise ObsError(f"{plan_slug}: step {step_number} must be an object")
        refs = step.get("instruction_slugs") or {}
        if not isinstance(refs, dict):
            raise ObsError(f"{plan_slug}: step {step_number} instruction_slugs must be an object")
        for label in ("role", "context", "specifics", "instructions"):
            values = refs.get(label, [])
            if isinstance(values, str):
                values = [values]
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                raise ObsError(f"{plan_slug}: step {step_number} instruction_slugs.{label} must be strings")
            for value in values:
                value = value.strip()
                if value and value not in seen:
                    seen.add(value)
                    found.append(value)
    return found


def _git_dirty(cwd: Path, relpath: str) -> bool:
    return relpath in set(__import__("obs.git", fromlist=["dirty_files"]).dirty_files(cwd))


def sync_plan(record: dict[str, Any], *, cwd: Path) -> dict[str, Any]:
    """Upload missing or Git-dirty plan/instruction records; never hash them."""
    from .instruction_upload import sync_instruction

    slug = str(record.get("record_identity") or record.get("slug") or "").strip()
    if not slug:
        raise ObsError("dispatch plan record missing record_identity")
    payload = _sync_payload(record, slug=slug)

    snapshot = pipeline_snapshot("control")
    instruction_registry = snapshot.get("registries", {}).get("instructions", {})
    remote_instruction_slugs = set(instruction_registry) if isinstance(instruction_registry, dict) else set()
    instruction_results: list[dict[str, Any]] = []
    for instruction_slug in _instruction_slugs(payload, plan_slug=slug):
        source = _single_slug_path(cwd, instruction_slug, label="instruction")
        relpath = source.relative_to(cwd.resolve()).as_posix()
        instruction_results.append(sync_instruction(
            cwd,
            slug=instruction_slug,
            path=str(source),
            source_path=relpath,
            remote_present=instruction_slug in remote_instruction_slugs,
            local_dirty=_git_dirty(cwd, relpath),
        ))

    plan_relpath = str(record.get("path") or "").strip()
    remote_plan_slugs = {item["slug"] for item in list_plans()}
    should_upload = slug not in remote_plan_slugs or (plan_relpath and _git_dirty(cwd, plan_relpath))
    if not should_upload:
        return {"slug": slug, "status": "current", "uploaded": False, "instructions": instruction_results}

    envelope = upload_record(type="plan", identity=slug, content=payload, extra={"source_path": plan_relpath} if plan_relpath else {})
    result = run([autoscribe_bin(), "upload", "plans"], cwd=cwd,
                 input_text=json.dumps(envelope, ensure_ascii=False) + "\n")
    return {
        "slug": slug,
        "status": "uploaded",
        "uploaded": True,
        "instructions": instruction_results,
        "pipeline_output": result.stdout.strip(),
    }
