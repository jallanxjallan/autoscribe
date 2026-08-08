from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .catalog import pipeline_snapshot
from .errors import ObsError
from .process import run
from .executables import autoscribe_bin
from .markdown import parse_markdown
from .contracts import upload_record

INSTRUCTION_LABELS = ("standing", "role", "context", "task")
INSTRUCTION_PREFIXES = ("std.", "rol.", "cxt.", "tsk.")


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
        if slug:
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
    slug = str(record.get("slug") or record.get("record_identity") or "<unknown>")
    raw_payload = record.get("payload")
    if raw_payload is not None:
        return {**record, **_decode_object(raw_payload, slug=slug, field="payload")}
    if "steps" in record and isinstance(record.get("steps"), dict):
        return dict(record)
    if "steps_json" not in record:
        raise ObsError(f"{slug}: control returned catalog metadata only")
    steps = _decode_object(record.get("steps_json"), slug=slug, field="steps_json")
    metadata = _decode_object(record.get("metadata_json", "{}"), slug=slug, field="metadata_json")
    return {**record, **metadata, "record_type": "plan", "record_identity": slug, "slug": slug, "steps": steps}


def load_plan(slug: str) -> dict[str, Any]:
    slug = slug.strip()
    if not slug:
        raise ObsError("plan.load requires slug")
    for record in list_plans():
        if record["slug"] == slug:
            return _materialize_plan(record)
    raise ObsError(f"plan not found in pipeline: {slug}")


def _inside(root: Path, path: Path) -> bool:
    root = root.resolve()
    path = path.resolve()
    return path == root or root in path.parents


def _ndjson(records: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records)


def _validate_steps(slug: str, content: dict[str, Any]) -> None:
    raw_steps = content.get("steps")
    if not isinstance(raw_steps, dict) or not raw_steps:
        raise ObsError(f"{slug}: plan steps must be a non-empty indexed object")
    ordered = sorted(raw_steps.items(), key=lambda item: int(str(item[0])) if str(item[0]).isdigit() else -1)
    actual = [int(str(key)) for key, _ in ordered if str(key).isdigit()]
    if actual != list(range(1, len(ordered) + 1)):
        raise ObsError(f"{slug}: plan step indexes must be contiguous from 1; got {actual}")
    for ordinal, (_, step) in enumerate(ordered, 1):
        if not isinstance(step, dict):
            raise ObsError(f"{slug}: step {ordinal} must be an object")
        refs = step.get("instruction_slugs") or {}
        if not isinstance(refs, dict):
            raise ObsError(f"{slug}: step {ordinal} instruction_slugs must be an object")
        legacy = sorted(set(refs) & {"specifics", "instructions"})
        if legacy:
            raise ObsError(f"{slug}: step {ordinal} uses legacy instruction labels: {', '.join(legacy)}")
        unknown = sorted(set(refs) - set(INSTRUCTION_LABELS))
        if unknown:
            raise ObsError(f"{slug}: step {ordinal} has unsupported instruction labels: {', '.join(unknown)}")
        for label in INSTRUCTION_LABELS:
            value = refs.get(label, [])
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ObsError(f"{slug}: step {ordinal} instruction_slugs.{label} must be a slug list")


def _instruction_records(cwd: Path, instruction_sets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for item in instruction_sets:
        slug = str(item.get("slug") or item.get("record_identity") or "").strip()
        if not slug.startswith(INSTRUCTION_PREFIXES):
            raise ObsError(f"invalid instruction slug: {slug or '<empty>'}")
        raw_path = str(item.get("abspath") or item.get("path") or "").strip()
        if not raw_path:
            raise ObsError(f"{slug}: instruction component requires path")
        source = Path(raw_path).expanduser()
        if not source.is_absolute():
            source = cwd / source
        source = source.resolve()
        if not source.is_file() or not _inside(cwd, source):
            raise ObsError(f"{slug}: instruction file is unavailable in the active vault: {source}")
        relpath = source.relative_to(cwd.resolve()).as_posix()
        document = parse_markdown(source.read_text(encoding="utf-8"))
        actual = str(document.frontmatter.get("slug") or "").strip()
        scope = str(document.frontmatter.get("scope") or "").strip().lower()
        if actual != slug:
            raise ObsError(f"{relpath}: expected slug {slug}, found {actual or '<empty>'}")
        if scope not in INSTRUCTION_LABELS:
            raise ObsError(f"{relpath}: invalid instruction scope {scope or '<empty>'}")
        if not document.body.strip():
            raise ObsError(f"{relpath}: instruction body is empty")
        record = upload_record(
            type="instruction",
            identity=slug,
            content=document.body,
            extra={
                "filename_hint": source.name,
                "source_path": relpath,
                "title": source.stem.strip(),
                "metadata": dict(document.frontmatter),
                "scope": scope,
            },
        )
        prior = unique.get(slug)
        if prior and prior["extra"]["source_path"] != relpath:
            raise ObsError(f"instruction slug {slug} resolves to multiple files")
        unique[slug] = record
    return list(unique.values())


def save_plan(
    record: dict[str, Any],
    *,
    cwd: Path,
    instruction_sets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Publish a complete plan snapshot and every referenced local instruction."""
    slug = str(record.get("record_identity") or record.get("slug") or "").strip()
    if not slug:
        raise ObsError("plan record missing record_identity")
    content = record.get("payload")
    if not isinstance(content, dict):
        raise ObsError(f"{slug}: plan.save requires payload object")
    content = {key: value for key, value in content.items() if key != "publication_ulid"}
    _validate_steps(slug, content)

    # Local wikilink-backed instruction files are reconciled through the same
    # sync path used by Library. Unchanged records are skipped; server-only
    # instruction slugs are never treated as files.
    from .instruction_upload import sync_instructions
    sync_results = sync_instructions(cwd, instruction_sets or []) if instruction_sets else []
    instructions = _instruction_records(cwd, instruction_sets or [])
    referenced = {
        value
        for step in content["steps"].values()
        for values in (step.get("instruction_slugs") or {}).values()
        for value in values
    }
    supplied = {record["identity"] for record in instructions}
    snapshot = pipeline_snapshot("control")
    registries = snapshot.get("registries", {}) if isinstance(snapshot, dict) else {}
    server_records = registries.get("instructions", {}) if isinstance(registries, dict) else {}
    if isinstance(server_records, dict):
        server_slugs = {str(key) for key in server_records}
    elif isinstance(server_records, list):
        server_slugs = {
            str(item.get("slug") or item.get("record_identity") or "").strip()
            for item in server_records
            if isinstance(item, dict)
        }
    else:
        server_slugs = set()
    available = supplied | server_slugs
    missing = sorted(referenced - available)
    if missing:
        raise ObsError(
            f"{slug}: referenced instructions are neither supplied locally nor present on the server: "
            + ", ".join(missing)
        )

    outputs: list[str] = []
    plan_record = upload_record(
        type="plan",
        identity=slug,
        content=content,
        extra={},
    )
    result = run([autoscribe_bin(), "upload", "plans"], cwd=cwd, input_text=_ndjson([plan_record]))
    if result.stdout.strip():
        outputs.append(result.stdout.strip())
    return {
        "record": plan_record,
        "instruction_count": len(instructions),
        "instructions": [record["identity"] for record in instructions],
        "instruction_sync": sync_results,
        "pipeline_output": "\n".join(outputs),
    }


def delete_plan(slug: str, *, cwd: Path) -> dict[str, Any]:
    command = os.environ.get("AUTOSCRIBE_DELETE_PLAN_COMMAND")
    if not command:
        raise ObsError("plan deletion is not configured; set AUTOSCRIBE_DELETE_PLAN_COMMAND")
    args = [part.format(slug=slug) for part in command.split()]
    result = run(args, cwd=cwd)
    return {"slug": slug, "pipeline_output": result.stdout.strip()}
