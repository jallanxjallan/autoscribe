from __future__ import annotations

import json
import subprocess
from pathlib import Path

from asc.control import repository


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args], check=True, text=True, stdout=subprocess.PIPE)
    return result.stdout.strip()


def _control_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "control"
    repo.mkdir()
    _git(repo, "init", "-q", "--initial-branch=master")
    _git(repo, "config", "user.email", "tests@autoscribe.local")
    _git(repo, "config", "user.name", "AutoScribe Tests")
    (repo / "instructions").mkdir()
    (repo / "engines").mkdir()
    (repo / "instructions/task.md").write_text(
        "---\nrecord: instruction\nslug: tsk.one\ntitle: Task One\ncomponent: task\n---\nDo the thing.\n"
    )
    (repo / "engines/chatgpt.py").write_text(
        'ENGINE_COMPONENT = {"kind":"llm","label":"ChatGPT","models":{"sol":"gpt-test"}}\n'
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "control")
    return repo


def _plan() -> dict:
    return {
        "record_type": "plan",
        "record_identity": "plan.one",
        "payload": {
            "label": "One",
            "steps": {
                "1": {
                    "index": 1,
                    "kind": "llm",
                    "engine": "chatgpt",
                    "model": "sol",
                    "instruction_slugs": {"task": ["tsk.one"]},
                }
            },
        },
    }


def test_plan_save_is_separate_from_authored_control_repo(tmp_path, monkeypatch):
    control = _control_repo(tmp_path)
    plans = tmp_path / "plans.git"
    monkeypatch.setenv("AUTOSCRIBE_CONTROL_REPO", str(control))
    monkeypatch.setenv("AUTOSCRIBE_PLAN_REPO", str(plans))
    monkeypatch.setenv("AUTOSCRIBE_CONTROL_REF", "master")
    monkeypatch.setenv("AUTOSCRIBE_PLAN_REF", "master")

    result = repository.save_plan(_plan())

    assert result["record_identity"] == "plan.one"
    assert not (control / "plans").exists()
    assert _git(control, "status", "--porcelain") == ""
    stored = repository.plan_records()
    assert [record["record_identity"] for record in stored] == ["plan.one"]


def test_instruction_catalog_reads_committed_git_not_redis(tmp_path, monkeypatch):
    control = _control_repo(tmp_path)
    monkeypatch.setenv("AUTOSCRIBE_CONTROL_REPO", str(control))
    monkeypatch.setenv("AUTOSCRIBE_CONTROL_REF", "master")

    records = repository.instruction_records()

    assert records == [{
        "type": "instruction",
        "slug": "tsk.one",
        "record_identity": "tsk.one",
        "title": "Task One",
        "label": "Task One",
        "description": "",
        "scope": "task",
        "component": "task",
        "path": "instructions/task.md",
        "source": "control-git",
        "repo_commit": _git(control, "rev-parse", "HEAD"),
    }]


def test_delete_plan_commits_only_to_plan_repo(tmp_path, monkeypatch):
    control = _control_repo(tmp_path)
    plans = tmp_path / "plans.git"
    monkeypatch.setenv("AUTOSCRIBE_CONTROL_REPO", str(control))
    monkeypatch.setenv("AUTOSCRIBE_PLAN_REPO", str(plans))
    repository.save_plan(_plan())

    repository.delete_plan("plan.one")

    assert repository.plan_records() == []
    assert not (control / "plans").exists()
