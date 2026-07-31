from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .contracts import enqueue_record, upload_record
from .errors import ObsError
from .executables import autoscribe_bin
from .markdown import parse_markdown, strip_frontmatter
from .process import run

RUN_PREFIX = "autoscribe/run/"
DISPATCH_MANIFEST = ".autoscribe/dispatch.json"
RESPONSE_MANIFEST = ".autoscribe/response.json"


@dataclass(frozen=True)
class TransportRun:
    branch: str
    manifest: dict[str, Any]

    @property
    def identity(self) -> str:
        return str(self.manifest.get("run_identity") or self.branch.removeprefix(RUN_PREFIX))


def _json_at_ref(repo: Path, branch: str, relpath: str) -> dict[str, Any] | None:
    result = run(["git", "show", f"{branch}:{relpath}"], cwd=repo, check=False)
    if result.returncode != 0:
        return None
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ObsError(f"{branch}:{relpath}: invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ObsError(f"{branch}:{relpath}: expected JSON object")
    return value


def waiting_runs(repo: Path) -> list[TransportRun]:
    output = run(
        ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/autoscribe/run/*"],
        cwd=repo,
    ).stdout
    items: list[TransportRun] = []
    for branch in sorted(line.strip() for line in output.splitlines() if line.strip()):
        manifest = _json_at_ref(repo, branch, DISPATCH_MANIFEST)
        if manifest is None:
            continue
        if _json_at_ref(repo, branch, RESPONSE_MANIFEST) is not None:
            continue
        items.append(TransportRun(branch=branch, manifest=manifest))
    return items


def _select_run(repo: Path, branch: str | None) -> TransportRun:
    runs = waiting_runs(repo)
    if branch:
        wanted = branch if branch.startswith(RUN_PREFIX) else RUN_PREFIX + branch
        for item in runs:
            if item.branch == wanted:
                return item
        raise ObsError(f"transport branch is absent or already completed: {wanted}")
    if not runs:
        raise ObsError("no waiting autoscribe/run/* branch found")
    if len(runs) > 1:
        names = "\n  ".join(item.branch for item in runs)
        raise ObsError(f"multiple runs are waiting; use --branch:\n  {names}")
    return runs[0]


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ObsError(f"could not read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ObsError(f"{path}: expected JSON object")
    return value


def _ndjson(records: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in records)


def _worktree(repo: Path, branch: str):
    class Worktree:
        def __enter__(self) -> Path:
            self.temp = tempfile.TemporaryDirectory(prefix="autoscribe-transport-")
            self.path = Path(self.temp.name) / "worktree"
            run(["git", "worktree", "add", "--quiet", str(self.path), branch], cwd=repo)
            return self.path

        def __exit__(self, exc_type, exc, tb) -> None:
            run(["git", "worktree", "remove", "--force", str(self.path)], cwd=repo, check=False)
            self.temp.cleanup()
    return Worktree()


def dispatch_run(repo: Path, *, branch: str | None = None, dry_run: bool = False) -> tuple[list[dict[str, Any]], str]:
    selected = _select_run(repo, branch)
    manifest = selected.manifest
    if manifest.get("branch") != selected.branch:
        raise ObsError(f"dispatch manifest branch mismatch: {manifest.get('branch')!r}")

    with _worktree(repo, selected.branch) as worktree:
        instruction_records: list[dict[str, Any]] = []
        for raw_path in manifest.get("instructions") or []:
            relpath = str(raw_path).strip()
            path = worktree / relpath
            if not path.is_file():
                raise ObsError(f"transport instruction missing: {relpath}")
            document = parse_markdown(path.read_text(encoding="utf-8"))
            identity = str(document.frontmatter.get("slug") or "").strip()
            if not identity:
                raise ObsError(f"{relpath}: instruction is missing slug")
            instruction_records.append(upload_record(
                type="instruction",
                identity=identity,
                content=document.body,
                extra={
                    "filename_hint": path.name,
                    "source_path": relpath,
                    "metadata": dict(document.frontmatter),
                    "run_identity": selected.identity,
                },
            ))

        plan_info = manifest.get("plan")
        if not isinstance(plan_info, dict):
            raise ObsError("dispatch.plan must be an object")
        plan_identity = str(plan_info.get("identity") or "").strip()
        plan_path = str(plan_info.get("path") or "").strip()
        if not plan_identity or not plan_path:
            raise ObsError("dispatch.plan requires identity and path")
        raw_plan = _read_json(worktree / plan_path)
        content = raw_plan.get("payload", raw_plan.get("content"))
        if not isinstance(content, dict):
            raise ObsError(f"{plan_path}: plan payload/content must be an object")
        plan_record = upload_record(
            type="plan",
            identity=plan_identity,
            content=content,
            extra={"filename_hint": Path(plan_path).name, "source_path": plan_path, "run_identity": selected.identity},
        )

        dispatch_commit = run(["git", "rev-parse", "HEAD"], cwd=worktree).stdout.strip()
        call_records: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        rows = manifest.get("records")
        if not isinstance(rows, list) or not rows:
            raise ObsError("dispatch.records must be a non-empty list")
        for raw in rows:
            if not isinstance(raw, dict):
                raise ObsError("dispatch record must be an object")
            identity = str(raw.get("identity") or "").strip()
            relpath = str(raw.get("source_path") or "").strip()
            if not identity or not relpath:
                raise ObsError("dispatch record requires identity and source_path")
            path = worktree / relpath
            if not path.is_file():
                raise ObsError(f"transport content missing: {relpath}")
            document = parse_markdown(path.read_text(encoding="utf-8"))
            actual = str(document.frontmatter.get("slug") or identity).strip()
            if actual != identity:
                raise ObsError(f"{relpath}: expected {identity}, found {actual}")
            call_records.append(upload_record(
                type="call",
                identity=identity,
                content=document.body,
                extra={
                    "filename_hint": path.name,
                    "source_path": relpath,
                    "metadata": dict(document.frontmatter),
                    "run_identity": selected.identity,
                    "transport_branch": selected.branch,
                    "dispatch_commit": dispatch_commit,
                },
            ))
            items.append({"slug": identity, "path": relpath, "branch": selected.branch})

        if dry_run:
            return items, ""

        outputs: list[str] = []
        for command, records in (
            ([autoscribe_bin(), "upload", "instructions"], instruction_records),
            ([autoscribe_bin(), "upload", "plans"], [plan_record]),
            ([autoscribe_bin(), "upload", "calls"], call_records),
        ):
            result = run(command, cwd=repo, input_text=_ndjson(records))
            if result.stdout.strip():
                outputs.append(result.stdout.strip())
        enqueue_rows = [enqueue_record(call=str(row["identity"]), plan=plan_identity) for row in call_records]
        result = run([autoscribe_bin(), "enqueue"], cwd=repo, input_text=_ndjson(enqueue_rows))
        if result.stdout.strip():
            outputs.append(result.stdout.strip())
        return items, "\n".join(outputs)


def _parse_ndjson(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ObsError(f"invalid NDJSON on line {number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ObsError(f"expected NDJSON object on line {number}")
        records.append(value)
    return records


def _first(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _decode(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _content(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("result_content", "record_content", "content", "body", "text"):
            if key in value:
                found = _content(value[key])
                if found:
                    return found
        return ""
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    return _content(parsed) or value


def export_results(repo: Path, *, branch: str | None = None, dry_run: bool = False) -> tuple[list[dict[str, Any]], str]:
    selected = _select_run(repo, branch)
    expected_rows = selected.manifest.get("records")
    if not isinstance(expected_rows, list) or not expected_rows:
        raise ObsError("dispatch.records must be a non-empty list")
    expected = {str(row.get("identity") or "").strip(): row for row in expected_rows if isinstance(row, dict)}
    if "" in expected:
        raise ObsError("dispatch record is missing identity")

    pending_raw = _parse_ndjson(run([autoscribe_bin(), "export", "extract-pending"], cwd=repo).stdout)
    results: dict[str, dict[str, Any]] = {}
    for raw in pending_raw:
        source_identity = _first(raw, "source_identity", "record_identity", "prompt_slug", "slug")
        if source_identity not in expected:
            continue
        extra = _decode(raw.get("extra_json"))
        if not extra:
            source_json = _decode(raw.get("source_json"))
            extra = _decode(source_json.get("extra_json")) or _decode(source_json.get("extra"))
        branch_hint = _first(extra, "transport_branch", "branch")
        run_hint = _first(extra, "run_identity")
        if branch_hint and branch_hint != selected.branch:
            continue
        if not branch_hint and run_hint and run_hint != selected.identity:
            continue
        content = _content(raw)
        if not content.strip():
            raise ObsError(f"{source_identity}: pending result content is empty")
        results[source_identity] = {
            "source_identity": source_identity,
            "call_identity": _first(raw, "call_identity", "identity"),
            "result_identity": _first(raw, "result_identity", "identity", "call_identity"),
            "result_key": _first(raw, "result_key"),
            "content": content,
        }

    missing = sorted(set(expected) - set(results))
    if missing:
        raise ObsError("run results are incomplete; missing: " + ", ".join(missing))

    items = [{"slug": slug, "path": str(expected[slug].get("source_path") or ""), "branch": selected.branch} for slug in sorted(expected)]
    if dry_run:
        return items, ""

    with _worktree(repo, selected.branch) as worktree:
        response_rows: list[dict[str, Any]] = []
        paths: list[str] = []
        for slug in sorted(expected):
            relpath = str(expected[slug].get("source_path") or "").strip()
            path = worktree / relpath
            if not path.is_file():
                raise ObsError(f"dispatch source is missing: {relpath}")
            document = parse_markdown(path.read_text(encoding="utf-8"))
            body = strip_frontmatter(results[slug]["content"]).lstrip("\n")
            if not body.strip():
                raise ObsError(f"{slug}: returned body is empty")
            rendered = document.frontmatter_text + body if document.has_frontmatter else body
            path.write_text(rendered, encoding="utf-8")
            paths.append(relpath)
            response_rows.append({
                "identity": slug,
                "source_path": relpath,
                "path": relpath,
                "call_identity": results[slug]["call_identity"],
                "result_identity": results[slug]["result_identity"],
                "result_key": results[slug]["result_key"] or None,
            })

        response = {
            "version": 1,
            "type": "autoscribe_response",
            "status": "completed",
            "run_identity": selected.identity,
            "branch": selected.branch,
            "dispatch_commit": run(["git", "rev-parse", "HEAD"], cwd=worktree).stdout.strip(),
            "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "records": response_rows,
        }
        response_path = worktree / RESPONSE_MANIFEST
        response_path.parent.mkdir(parents=True, exist_ok=True)
        response_path.write_text(json.dumps(response, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        run(["git", "add", "--", *paths, RESPONSE_MANIFEST], cwd=worktree)
        changed = run(["git", "diff", "--cached", "--quiet"], cwd=worktree, check=False)
        if changed.returncode == 0:
            raise ObsError("response materialization produced no Git changes")
        run(["git", "commit", "--quiet", "-m", f"RESPONSE {selected.identity}"], cwd=worktree)
        commit = run(["git", "rev-parse", "HEAD"], cwd=worktree).stdout.strip()

    for result in results.values():
        receipt = result["result_key"] or result["result_identity"]
        run(
            [autoscribe_bin(), "export", "update-exports", receipt, "--export-message", f"git-transport:{selected.identity}"],
            cwd=repo,
        )
    return items, commit
