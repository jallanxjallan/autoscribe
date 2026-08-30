from __future__ import annotations

import json
import subprocess
from pathlib import Path

from asc.ingest.common import IngestedItem
from asc.ingest import git_revision


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, text=True, stdout=subprocess.PIPE)
    return result.stdout.strip()


def _work_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "work"
    repo.mkdir()
    _git(repo, "init", "-q", "--initial-branch=main")
    _git(repo, "config", "user.email", "tests@autoscribe.local")
    _git(repo, "config", "user.name", "AutoScribe Tests")
    return repo


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _item(path: str) -> IngestedItem:
    kind = "instruction" if path.startswith("instructions/") else "plan"
    return IngestedItem(record_type=kind, slug=Path(path).stem, key=f"{kind}:01TEST")


def test_incremental_ingest_reads_only_changed_config_paths(tmp_path, monkeypatch):
    repo = _work_repo(tmp_path)
    (repo / "instructions").mkdir()
    (repo / "plans").mkdir()
    (repo / "notes").mkdir()
    (repo / "instructions/one.json").write_text(json.dumps({"type":"instruction","identity":"tsk.one","content":"one"}))
    (repo / "plans/one.json").write_text(json.dumps({"record_identity":"plan.one","payload":{"steps":{}}}))
    (repo / "notes/ignored.txt").write_text("old")
    base = _commit(repo, "base")

    (repo / "instructions/one.json").write_text(json.dumps({"type":"instruction","identity":"tsk.one","content":"changed"}))
    (repo / "notes/ignored.txt").write_text("new")
    head = _commit(repo, "change")

    seen = []
    monkeypatch.setattr(git_revision, "_ingest_path", lambda _repo, _commit, path: seen.append(path) or _item(path))
    report = git_revision.ingest_git_revision(repo, head, base=base)

    assert seen == ["instructions/one.json"]
    assert report.record_count == 1


def test_ingest_accepts_bare_server_repository(tmp_path, monkeypatch):
    work = _work_repo(tmp_path)
    (work / "plans").mkdir()
    (work / "plans/one.json").write_text(json.dumps({"record_identity":"plan.one","payload":{"steps":{}}}))
    head = _commit(work, "plan")
    bare = tmp_path / "server.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)], check=True)

    seen = []
    monkeypatch.setattr(git_revision, "_ingest_path", lambda _repo, _commit, path: seen.append(path) or _item(path))
    report = git_revision.ingest_git_revision(bare, head, full=True)

    assert seen == ["plans/one.json"]
    assert report.record_count == 1
