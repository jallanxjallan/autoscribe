from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import enqueue_record, upload_record
from .errors import ObsError
from .executables import autoscribe_bin
from .markdown import parse_markdown
from .process import run

RUN_PREFIX = "autoscribe/run/"
CLAIMED_PREFIX = "autoscribe/claimed/"


@dataclass(frozen=True)
class TransportRun:
    branch: str
    metadata: dict[str, Any]
    dispatch_commit: str

    @property
    def identity(self) -> str:
        return str(self.metadata.get("run_identity") or self.branch.removeprefix(RUN_PREFIX))

    @property
    def manifest(self) -> dict[str, Any]:
        """Compatibility alias while callers migrate from file manifests."""
        return self.metadata


def _safe_tag_part(value: str) -> str:
    import re
    result = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-")
    return result or "unknown"


def _tag_exists(repo: Path, tag: str) -> bool:
    return run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{tag}"], cwd=repo, check=False).returncode == 0


def _dispatch_commit(repo: Path, branch: str) -> str:
    output = run(["git", "log", "--format=%H%x09%s", branch], cwd=repo).stdout
    for line in output.splitlines():
        commit, _, subject = line.partition("\t")
        if subject.strip() == "AUTOSCRIBE DISPATCH":
            return commit.strip()
    return ""


def _parse_dispatch_message(message: str, branch: str) -> dict[str, Any]:
    lines = message.splitlines()
    if not lines or lines[0].strip() != "AUTOSCRIBE DISPATCH":
        raise ObsError(f"{branch}: dispatch commit has an invalid subject")
    values: dict[str, str] = {}
    records: list[dict[str, str]] = []
    instructions: list[str] = []
    for line in lines[1:]:
        key, marker, raw = line.partition(":")
        if not marker:
            continue
        value = raw.strip()
        if key == "Record":
            identity, tab, source_path = value.partition("\t")
            if not tab or not identity.strip() or not source_path.strip():
                raise ObsError(f"{branch}: malformed Record line in dispatch commit")
            records.append({"identity": identity.strip(), "source_path": source_path.strip()})
        elif key == "Instruction":
            if value:
                instructions.append(value)
        else:
            values[key] = value
    metadata: dict[str, Any] = {
        "run_identity": values.get("Run") or branch.removeprefix(RUN_PREFIX),
        "branch": branch,
        "created_at": values.get("Created") or None,
        "source_branch": values.get("Source-Branch") or None,
        "source_commit": values.get("Source-Commit") or None,
        "plan": {"identity": values.get("Plan") or "", "path": values.get("Plan-Path") or ""},
        "records": records,
        "instructions": instructions,
    }
    if values.get("Combine-Basename"):
        metadata["combine"] = {"basename": values["Combine-Basename"]}
    return metadata


def _transport_run(repo: Path, branch: str) -> TransportRun | None:
    commit = _dispatch_commit(repo, branch)
    if not commit:
        return None
    message = run(["git", "show", "-s", "--format=%B", commit], cwd=repo).stdout
    return TransportRun(branch=branch, metadata=_parse_dispatch_message(message, branch), dispatch_commit=commit)


def all_runs(repo: Path) -> list[TransportRun]:
    output = run(["git", "for-each-ref", "--format=%(refname:short)", "refs/heads/autoscribe/run/*"], cwd=repo).stdout
    items: list[TransportRun] = []
    for branch in sorted(line.strip() for line in output.splitlines() if line.strip()):
        item = _transport_run(repo, branch)
        if item is not None:
            items.append(item)
    return items


def waiting_runs(repo: Path) -> list[TransportRun]:
    return [item for item in all_runs(repo) if not _tag_exists(repo, CLAIMED_PREFIX + _safe_tag_part(item.identity))]


def claimed_runs(repo: Path) -> list[TransportRun]:
    return [item for item in all_runs(repo) if _tag_exists(repo, CLAIMED_PREFIX + _safe_tag_part(item.identity))]


def _select_run(repo: Path, branch: str | None) -> TransportRun:
    runs = waiting_runs(repo)
    if branch:
        wanted = branch if branch.startswith(RUN_PREFIX) else RUN_PREFIX + branch
        for item in runs:
            if item.branch == wanted:
                return item
        raise ObsError(f"transport branch is absent or already claimed: {wanted}")
    if not runs:
        raise ObsError("no unclaimed autoscribe/run/* branch found")
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
    """Upload calls from a transport branch and enqueue against a published plan.

    Plan and instruction publication is owned by Define Plan. Dispatch never
    discovers, reads, or uploads plan components.
    """
    selected = _select_run(repo, branch)
    metadata = selected.metadata
    with _worktree(repo, selected.branch) as worktree:
        plan_info = metadata.get("plan")
        if not isinstance(plan_info, dict):
            raise ObsError("dispatch plan metadata is missing")
        plan_identity = str(plan_info.get("identity") or "").strip()
        if not plan_identity:
            raise ObsError("dispatch commit requires Plan")

        call_records: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        rows = metadata.get("records")
        if not isinstance(rows, list) or not rows:
            raise ObsError("dispatch commit must contain at least one Record line")
        for raw in rows:
            identity = str(raw.get("identity") or "").strip()
            relpath = str(raw.get("source_path") or "").strip()
            path = worktree / relpath
            if not identity or not relpath or not path.is_file():
                raise ObsError(f"invalid or missing transport record: {identity or relpath}")
            document = parse_markdown(path.read_text(encoding="utf-8"))
            actual = str(document.frontmatter.get("slug") or identity).strip()
            if actual != identity:
                raise ObsError(f"{relpath}: expected {identity}, found {actual}")
            call_records.append(upload_record(type="call", identity=identity, content=document.body,
                extra={"filename_hint": path.name, "source_path": relpath, "metadata": dict(document.frontmatter),
                       "run_identity": selected.identity, "transport_branch": selected.branch, "dispatch_commit": selected.dispatch_commit}))
            items.append({"slug": identity, "path": relpath, "branch": selected.branch})

        if dry_run:
            return items, ""
        outputs: list[str] = []
        result = run([autoscribe_bin(), "upload", "calls"], cwd=repo, input_text=_ndjson(call_records))
        if result.stdout.strip():
            outputs.append(result.stdout.strip())
        enqueue_rows = [enqueue_record(call=str(row["identity"]), plan=plan_identity) for row in call_records]
        result = run([autoscribe_bin(), "enqueue"], cwd=repo, input_text=_ndjson(enqueue_rows))
        if result.stdout.strip():
            outputs.append(result.stdout.strip())
        tag = CLAIMED_PREFIX + _safe_tag_part(selected.identity)
        run(["git", "tag", "-f", "-a", tag, selected.dispatch_commit, "-m", f"AutoScribe run claimed: {selected.identity}"], cwd=repo)
        return items, "\n".join(outputs)
