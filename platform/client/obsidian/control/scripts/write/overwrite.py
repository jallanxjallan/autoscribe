"""NDJSON writeback execution for the current registered vault."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable

from git.git import GitRepo, NotAGitRepositoryError
from records.files import overwrite_text
from vault.discover import VaultRuntimeError, discover_registered_vault_root
from write.common import WriteError, WriteRecord, iter_input_records

_SLUG_LINE_RE = re.compile(r"^slug:\s*(?P<slug>.+?)\s*$")


@dataclass(frozen=True)
class WritebackPlan:
    path: Path
    slug: str
    replacement_text: str


def writeback(
    *,
    input_stream: Iterable[str],
    cwd: Path | None = None,
) -> list[Path]:
    records = list(iter_input_records(input_stream))
    vault_root = _discover_current_vault_root(cwd=cwd)
    slug_map = _build_local_slug_map(vault_root)
    return _writeback_records(records, slug_map)


def _writeback_records(records: list[WriteRecord], slug_map: dict[str, Path]) -> list[Path]:
    plans = _build_writeback_plans(records, slug_map)
    _apply_writeback_plans(plans)
    _clear_conflict_markers(plans)
    _commit_writeback_plans(plans)

    for plan in plans:
        print(f"WRITEBACK: {plan.slug} -> {plan.path}", file=sys.stderr)

    return [plan.path for plan in plans]


def _build_writeback_plans(
    records: list[WriteRecord],
    slug_map: dict[str, Path],
) -> list[WritebackPlan]:
    resolved_targets: list[tuple[int, WriteRecord, Path]] = []
    seen_paths: set[Path] = set()

    for index, record in enumerate(records, start=1):
        slug = record.input_record.slug
        if slug is None:
            print(
                f"WRITEBACK: skipping record {index}: missing input_record.metadata.slug",
                file=sys.stderr,
            )
            continue

        path = slug_map.get(slug)
        if path is None:
            raise WriteError(f"record {index}: slug resolution error: {slug} matched 0 files")
        if not path.exists():
            raise WriteError(f"missing target file for slug: {slug}")
        if path in seen_paths:
            raise WriteError(f"record {index}: duplicate target path: {path}")
        seen_paths.add(path)
        resolved_targets.append((index, record, path))

    dirty_paths_by_repo = _dirty_paths_by_repo([path for _, _, path in resolved_targets])

    plans: list[WritebackPlan] = []
    for index, record, path in resolved_targets:
        slug = record.input_record.slug
        assert slug is not None

        repo = _discover_git_repo(path)
        if path.resolve() in dirty_paths_by_repo[repo.root]:
            _write_conflict_marker(path=path, slug=slug)
            raise WriteError(f"conflicted: attempted to overwrite editing file: {path}")

        try:
            original_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise WriteError(f"writeback failed: {slug} -> {path}: {exc}") from exc

        replacement_text = _build_writeback_content(
            path=path,
            original_text=original_text,
            new_content=record.content,
        )
        plans.append(
            WritebackPlan(
                path=path,
                slug=slug,
                replacement_text=replacement_text,
            )
        )

    return plans


def _apply_writeback_plans(plans: list[WritebackPlan]) -> None:
    for plan in plans:
        try:
            overwrite_text(plan.path, plan.replacement_text)
        except OSError as exc:
            raise WriteError(f"writeback failed: {plan.slug} -> {plan.path}: {exc}") from exc


def _build_writeback_content(
    *,
    path: Path,
    original_text: str,
    new_content: str,
) -> str:
    if not original_text.startswith("---"):
        return new_content

    _, _, remainder = original_text.partition("---")
    raw_frontmatter, delimiter, _ = remainder.partition("---")
    if not delimiter:
        raise WriteError(f"invalid frontmatter in target file: {path}: missing closing delimiter")

    return f"---{raw_frontmatter}---\n\n{new_content}"


def _discover_current_vault_root(*, cwd: Path | None) -> Path:
    working_dir = (cwd or Path.cwd()).expanduser().resolve()
    try:
        return discover_registered_vault_root(working_dir)
    except VaultRuntimeError as exc:
        raise WriteError(str(exc)) from exc


def _build_local_slug_map(vault_root: Path) -> dict[str, Path]:
    slug_map: dict[str, Path] = {}

    for entry in _scan_local_slug_entries(vault_root):
        slug = entry["slug"]
        path = Path(entry["path"]).expanduser().resolve()
        existing = slug_map.get(slug)
        if existing is not None and existing != path:
            raise WriteError(f"duplicate slug in current vault: {slug}: {existing} and {path}")
        slug_map[slug] = path

    return slug_map


def _scan_local_slug_entries(vault_root: Path) -> list[dict[str, str]]:
    proc = subprocess.run(
        [
            "rg",
            "--json",
            "--glob",
            "*.md",
            r"^slug:\s*.+\s*$",
            ".",
        ],
        cwd=str(vault_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode not in {0, 1}:
        detail = proc.stderr.strip() or proc.stdout.strip() or "rg failed"
        raise WriteError(f"local slug scan failed: {detail}")

    results: list[dict[str, str]] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise WriteError(f"local slug scan failed: invalid rg json: {exc}") from exc
        if event.get("type") != "match":
            continue

        data = event.get("data") or {}
        path_text = (data.get("path") or {}).get("text")
        line_text = (data.get("lines") or {}).get("text")
        if not isinstance(path_text, str) or not isinstance(line_text, str):
            continue

        match = _SLUG_LINE_RE.match(line_text.rstrip("\r\n"))
        if match is None:
            continue

        results.append(
            {
                "slug": match.group("slug").strip(),
                "path": str((vault_root / path_text).expanduser().resolve()),
            }
        )

    return results


def _dirty_paths_by_repo(paths: list[Path]) -> dict[Path, set[Path]]:
    grouped_paths: dict[Path, list[Path]] = {}
    repos: dict[Path, GitRepo] = {}

    for path in paths:
        repo = _discover_git_repo(path)
        grouped_paths.setdefault(repo.root, []).append(path)
        repos[repo.root] = repo

    dirty_paths_by_repo: dict[Path, set[Path]] = {}
    for repo_root, repo_paths in grouped_paths.items():
        dirty_paths: set[Path] = set()
        for entry in repos[repo_root].status_for_paths(repo_paths):
            if entry.is_ignored or not entry.is_dirty:
                continue
            dirty_paths.add(entry.path.resolve())
            if entry.original_path is not None:
                dirty_paths.add(entry.original_path.resolve())
        dirty_paths_by_repo[repo_root] = dirty_paths

    return dirty_paths_by_repo


def _workflow_marker_name(path: Path) -> str:
    return str(path.expanduser().resolve()).replace("/", "__")


def _conflict_marker_path(path: Path) -> Path:
    repo = _discover_git_repo(path)
    return (
        repo.root
        / ".autoscribe"
        / "workflow"
        / "conflicts"
        / f"{_workflow_marker_name(path)}.json"
    )


def _write_conflict_marker(*, path: Path, slug: str) -> None:
    marker = _conflict_marker_path(path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "repo_state": "conflicted",
                "slug": slug,
                "path": str(path),
                "reason": "attempted to overwrite editing file",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _clear_conflict_markers(plans: list[WritebackPlan]) -> None:
    for plan in plans:
        marker = _conflict_marker_path(plan.path)
        if marker.exists():
            marker.unlink()


def _commit_writeback_plans(plans: list[WritebackPlan]) -> None:
    by_repo: dict[Path, list[WritebackPlan]] = {}

    for plan in plans:
        repo = _discover_git_repo(plan.path)
        by_repo.setdefault(repo.root, []).append(plan)

    for repo_root, repo_plans in by_repo.items():
        rel_paths = [
            str(plan.path.expanduser().resolve().relative_to(repo_root))
            for plan in repo_plans
        ]

        _run_git(["add", "--", *rel_paths], cwd=repo_root)

        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--", *rel_paths],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )

        if diff.returncode == 0:
            continue
        if diff.returncode != 1:
            detail = diff.stderr.strip() or diff.stdout.strip() or "git diff failed"
            raise WriteError(f"writeback commit preflight failed: {detail}")

        slugs = ", ".join(plan.slug for plan in repo_plans)
        _run_git(["commit", "-m", f"autoscribe: writeback {slugs}", "--", *rel_paths], cwd=repo_root)


def _run_git(argv: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", *argv],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or proc.stdout.strip() or "git failed"
        raise WriteError(f"git {' '.join(argv)} failed: {detail}")
    return proc


def _discover_git_repo(path: Path) -> GitRepo:
    try:
        return GitRepo.discover(path)
    except NotAGitRepositoryError as exc:
        raise WriteError(f"writeback requires a git worktree for editing-file detection: {path}") from exc
