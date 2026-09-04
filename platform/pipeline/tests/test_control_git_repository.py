from __future__ import annotations

import json
import subprocess
from pathlib import Path

from asc.config.repos import ControlRepoConfig
from asc.control import repository


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout.strip()


def _control_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "control"
    repo.mkdir()
    _git(repo, "init", "-q", "--initial-branch=master")
    _git(repo, "config", "user.email", "tests@autoscribe.local")
    _git(repo, "config", "user.name", "AutoScribe Tests")
    (repo / "instructions").mkdir()
    (repo / "context").mkdir()
    (repo / "plans").mkdir()
    (repo / "instructions/task.md").write_text(
        "---\nrecord: instruction\nslug: tsk.one\ntitle: Task One\ncomponent: task\n---\nDo the thing.\n"
    )
    (repo / "context/project.md").write_text(
        "---\ntype: instruction\nslug: ctx.project\ntitle: Project Context\ncomponent: context\n---\nProject facts.\n"
    )
    (repo / "plans/one.json").write_text(
        json.dumps({
            "record_type": "plan",
            "record_identity": "plan.one",
            "record_content": {
                "steps": {
                    "1": {
                        "kind": "llm",
                        "engine": "chatgpt",
                        "instruction_slugs": {"task": "tsk.one"},
                    }
                }
            },
        })
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "control")
    return repo


def _configure(monkeypatch, repo: Path) -> None:
    monkeypatch.setattr(
        repository,
        "CONTROL",
        ControlRepoConfig(repo, "master", "AutoScribe Tests", "tests@autoscribe.local"),
    )


def test_plan_is_read_directly_from_current_control_git(tmp_path, monkeypatch):
    control = _control_repo(tmp_path)
    _configure(monkeypatch, control)

    loaded = repository.read_plan("plan.one")

    assert loaded.slug == "plan.one"
    assert loaded.path == "plans/one.json"
    assert loaded.revision == _git(control, "rev-parse", "HEAD")
    assert loaded.plan.identity == "plan.one"
    assert loaded.plan.step_definition(1)["instruction_slugs"] == {"task": "tsk.one"}


def test_plan_read_observes_new_commit_without_redis_refresh(tmp_path, monkeypatch):
    control = _control_repo(tmp_path)
    _configure(monkeypatch, control)
    first = repository.read_plan("plan.one")
    path = control / "plans/one.json"
    record = json.loads(path.read_text())
    record["record_content"]["steps"]["1"]["model"] = "new-model"
    path.write_text(json.dumps(record))
    _git(control, "add", "plans/one.json")
    _git(control, "commit", "-q", "-m", "update plan")

    second = repository.read_plan("plan.one")

    assert second.revision != first.revision
    assert second.plan.step_definition(1)["model"] == "new-model"


def test_instruction_read_includes_last_git_change_timestamp(tmp_path, monkeypatch):
    control = _control_repo(tmp_path)
    _configure(monkeypatch, control)

    instruction = repository.read_instruction("tsk.one")

    assert instruction.content == "Do the thing."
    assert instruction.path == "instructions/task.md"
    assert instruction.commit_timestamp == int(
        _git(control, "log", "-1", "--format=%ct", "HEAD", "--", instruction.path)
    )


def test_context_instruction_is_read_from_current_control_git(tmp_path, monkeypatch):
    control = _control_repo(tmp_path)
    _configure(monkeypatch, control)

    instruction = repository.read_instruction("ctx.project")

    assert instruction.content == "Project facts."
    assert instruction.path == "context/project.md"
    assert instruction.extra["component"] == "context"
