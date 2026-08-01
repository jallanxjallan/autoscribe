from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import ObsError
from .executables import autoscribe_bin
from .process import run
from .transport import RUN_PREFIX, TransportRun, _worktree, waiting_runs

RESULTS_DIR = ".autoscribe/results"
RETRIEVAL_STATUS = ".autoscribe/retrieval.json"


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


def _content(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("record_content", "result_content", "content", "body", "text"):
            if key in value:
                found = _content(value[key])
                if found:
                    return found
        return ""
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return value
    return _content(decoded) or value


def _selected_runs(repo: Path, branch: str | None) -> list[TransportRun]:
    runs = waiting_runs(repo)
    if not branch:
        if not runs:
            raise ObsError("no waiting autoscribe/run/* branch found")
        return runs

    wanted = branch if branch.startswith(RUN_PREFIX) else RUN_PREFIX + branch
    for item in runs:
        if item.branch == wanted:
            return [item]
    raise ObsError(f"transport branch is absent or already completed: {wanted}")


def _flight_records(flight: TransportRun) -> list[dict[str, str]]:
    rows = flight.manifest.get("records")
    if not isinstance(rows, list) or not rows:
        raise ObsError(f"{flight.branch}: dispatch.records must be a non-empty list")

    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            raise ObsError(f"{flight.branch}: dispatch record must be an object")
        identity = str(raw.get("identity") or "").strip()
        source_path = str(raw.get("source_path") or "").strip()
        if not identity:
            raise ObsError(f"{flight.branch}: dispatch record is missing identity")
        if identity in seen:
            raise ObsError(f"{flight.branch}: duplicate dispatch identity: {identity}")
        seen.add(identity)
        records.append({"identity": identity, "source_path": source_path})
    return records


def _result_path(worktree: Path, identity: str) -> Path:
    # Slugs are already constrained identifiers in feeder manifests. Reject path
    # separators rather than silently mapping a malformed identity elsewhere.
    if "/" in identity or "\\" in identity or identity in {".", ".."}:
        raise ObsError(f"invalid record identity for result storage: {identity!r}")
    return worktree / RESULTS_DIR / f"{identity}.json"


def _normalise_result(
    raw: dict[str, Any],
    *,
    identity: str,
    source_path: str,
    flight: TransportRun,
) -> dict[str, Any]:
    item = dict(raw)
    item["record_identity"] = identity
    item.setdefault("source_identity", identity)
    item["source_path"] = source_path
    item["transport_branch"] = flight.branch
    item["run_identity"] = flight.identity
    return item


def retrieve_results(
    repo: Path,
    *,
    branch: str | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Retrieve available results for waiting flights and store them in each branch.

    Feeder sends one slug list per flight to ``asc export extract-selected``.
    Exporter may return any completed subset. Returned records are committed under
    ``.autoscribe/results``; absent records remain missing and may be retrieved on
    a later run. Existing branch results are skipped unless ``force`` is true.
    """

    report: dict[str, list[dict[str, Any]]] = {
        "downloaded": [],
        "missing": [],
        "already_downloaded": [],
    }

    for flight in _selected_runs(repo, branch):
        expected_rows = _flight_records(flight)
        paths = {row["identity"]: row["source_path"] for row in expected_rows}

        with _worktree(repo, flight.branch) as worktree:
            existing = {
                identity
                for identity in paths
                if _result_path(worktree, identity).is_file()
            }
            eligible = list(paths) if force else [identity for identity in paths if identity not in existing]

            for identity in paths:
                if identity in existing and not force:
                    report["already_downloaded"].append({
                        "record_identity": identity,
                        "source_path": paths[identity],
                        "transport_branch": flight.branch,
                        "run_identity": flight.identity,
                    })

            if dry_run:
                for identity in eligible:
                    report["missing"].append({
                        "record_identity": identity,
                        "source_path": paths[identity],
                        "transport_branch": flight.branch,
                        "run_identity": flight.identity,
                    })
                continue

            if not eligible:
                continue

            output = run(
                [autoscribe_bin(), "export", "extract-selected", *eligible],
                cwd=repo,
            ).stdout
            rows = _parse_ndjson(output)
            by_identity: dict[str, dict[str, Any]] = {}
            for index, raw in enumerate(rows, 1):
                identity = _first(raw, "record_identity", "source_identity", "prompt_slug", "slug")
                if not identity:
                    raise ObsError(f"{flight.branch}: extracted result {index} is missing source identity")
                if identity not in paths:
                    raise ObsError(f"{flight.branch}: exporter returned unexpected identity: {identity}")
                if identity in by_identity:
                    raise ObsError(f"{flight.branch}: exporter returned duplicate identity: {identity}")
                if not _content(raw).strip():
                    raise ObsError(f"{flight.branch}: {identity}: extracted result content is empty")
                by_identity[identity] = raw

            downloaded: list[dict[str, Any]] = []
            for identity in eligible:
                raw = by_identity.get(identity)
                if raw is None:
                    report["missing"].append({
                        "record_identity": identity,
                        "source_path": paths[identity],
                        "transport_branch": flight.branch,
                        "run_identity": flight.identity,
                    })
                    continue

                item = _normalise_result(
                    raw,
                    identity=identity,
                    source_path=paths[identity],
                    flight=flight,
                )
                result_path = _result_path(worktree, identity)
                result_path.parent.mkdir(parents=True, exist_ok=True)
                result_path.write_text(
                    json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                downloaded.append(item)
                report["downloaded"].append(item)

            status = {
                "branch": flight.branch,
                "run_identity": flight.identity,
                "downloaded": sorted(
                    identity for identity in paths if _result_path(worktree, identity).is_file()
                ),
                "missing": sorted(
                    identity for identity in paths if not _result_path(worktree, identity).is_file()
                ),
            }
            status_path = worktree / RETRIEVAL_STATUS
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(
                json.dumps(status, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            add_paths = [RETRIEVAL_STATUS]
            add_paths.extend(
                str(_result_path(worktree, item["record_identity"]).relative_to(worktree))
                for item in downloaded
            )
            run(["git", "add", *add_paths], cwd=worktree)
            changed = run(["git", "diff", "--cached", "--quiet"], cwd=worktree, check=False).returncode != 0
            if changed:
                count = len(downloaded)
                run(
                    ["git", "commit", "-m", f"RETRIEVE {flight.identity}: {count} result(s)"],
                    cwd=worktree,
                )

    return report
