from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from asc.config.repos import ControlRepoConfig
from asc.control import repository
from asc.enqueue.plan import load_plan
from asc.enqueue import runtime
from asc.models.control.plan import instruction_scope

ROLE = "rol_4Q7M2V9K8D3R6X1P"
CONTEXT = "ctx_8J2F6R4W9P1C7T5N"
TASK = "spc_3N6K8R2V7M4Q9D1X"


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        [sys.executable, str(repository.GIT), "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _record():
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    return {
        "slug": "plan.one",
        "title": "One",
        "description": "",
        "steps": {
            "1": {
                "engine_kind": "llm",
                "engine": "chatgpt",
                "model": "cheap",
                "instructions": {"role": [ROLE], "context": [CONTEXT], "task": [TASK]},
                "args": {},
            }
        },
        "capabilities": {
            "engines": {
                "chatgpt": {
                    "kind": "llm",
                    "step_fields": ["model", "temperature", "max_output_tokens"],
                    "args_schema": schema,
                }
            },
            "models": {"cheap": {"engine": "chatgpt", "args_schema": schema}},
            "local_scripts": {},
            "rag_profiles": {},
        },
    }


def _instruction(identity, title="Some title", body="Do the thing.\n"):
    return f'---\nidentity: {identity}\ntitle: {title}\ndescription: ""\n---\n{body}'


def _commit(repo):
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "control")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def control(tmp_path, monkeypatch):
    repo = tmp_path / "control"
    repo.mkdir()
    _git(repo, "init", "-q", "--initial-branch=master")
    _git(repo, "config", "user.email", "tests@autoscribe.local")
    _git(repo, "config", "user.name", "AutoScribe Tests")
    for directory in ("instructions", "context", "plans"):
        (repo / directory).mkdir()
    for name, identity in (
        ("instructions/role.md", ROLE),
        ("context/project.md", CONTEXT),
        ("instructions/task.md", TASK),
    ):
        (repo / name).write_text(_instruction(identity))
    (repo / "plans/one.json").write_text(json.dumps(_record()))
    _commit(repo)
    monkeypatch.setattr(
        repository, "CONTROL", ControlRepoConfig(repo, "master", "Tests", "tests@local")
    )
    return repo


def test_bare_repository_reads_and_blob_version(control, tmp_path, monkeypatch):
    bare = tmp_path / "control.git"
    _git(control, "clone", "--bare", str(control), str(bare))
    monkeypatch.setattr(
        repository, "CONTROL", ControlRepoConfig(bare, "master", "Tests", "tests@local")
    )
    loaded = load_plan("plan.one")
    instruction = repository.read_instruction(TASK, loaded.revision)
    assert loaded.plan.identity == "plan.one"
    assert instruction.identity == TASK
    assert instruction.content == "Do the thing.\n"
    assert instruction.fingerprint == _git(
        bare, "rev-parse", f"{loaded.revision}:instructions/task.md"
    )
    assert not hasattr(repository, "control_checkout")


def test_revision_pinning_through_runtime_materialization(control, monkeypatch):
    loaded = load_plan("plan.one")
    path = control / "instructions/task.md"
    path.write_text(_instruction(TASK, body="Changed at B.\n"))
    revision_b = _commit(control)
    seen = []

    def resolve(identity, *, control_revision):
        source = repository.read_instruction(identity, control_revision)
        seen.append(source)
        return f"instruction:{identity}:record"

    monkeypatch.setattr(runtime, "resolve_instruction_key", resolve)
    monkeypatch.setattr(runtime.Runtime, "save", lambda self, **kwargs: self.raw_key)
    runtimes = runtime.materialize_runtimes(
        call_identity="runtime-call", plan=loaded.plan, control_revision=loaded.revision
    )
    assert all(source.revision == loaded.revision for source in seen)
    assert seen[-1].content == "Do the thing.\n"
    assert runtimes[0].plan_identity == "plan.one"
    assert repository.read_instruction(TASK, revision_b).content == "Changed at B.\n"


def test_filename_and_title_are_nonsemantic(control):
    old = repository.read_instruction(TASK, repository.control_revision())
    path = control / "instructions/task.md"
    path.rename(control / "instructions/unrelated.md")
    (control / "instructions/unrelated.md").write_text(
        _instruction(TASK, title="Renamed")
    )
    revision = _commit(control)
    new = repository.read_instruction(TASK, revision)
    assert new.identity == old.identity
    assert new.title == "Renamed"
    assert new.fingerprint != old.fingerprint


@pytest.mark.parametrize("identity", [ROLE, CONTEXT, TASK])
def test_valid_identities(identity):
    assert instruction_scope(identity) in {"role", "context", "task"}


@pytest.mark.parametrize(
    "identity",
    [
        "tsk_3N6K8R2V7M4Q9D1X",
        "spc_3n6k8r2v7m4q9d1x",
        "spc_3N6K8R2V7M4Q9D1I",
        "ctx_123",
        "ctx_8J2F6R4W9P1C7T5U",
        "tsk.one",
        "",
        None,
    ],
)
def test_invalid_identities(identity):
    with pytest.raises(ValueError):
        instruction_scope(identity)


def test_duplicate_instruction_rejects_revision(control):
    (control / "context/duplicate.md").write_text(_instruction(TASK))
    _commit(control)
    with pytest.raises(ValueError, match="duplicate instruction"):
        load_plan("plan.one")


def test_duplicate_plan_rejects_revision(control):
    (control / "plans/duplicate.json").write_text(json.dumps(_record()))
    _commit(control)
    with pytest.raises(ValueError, match="duplicate plan"):
        load_plan("plan.one")


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(record_identity=r.pop("slug")),
        lambda r: r.update(payload={"steps": r.pop("steps")}),
        lambda r: r["steps"]["1"].update(instruction_slugs={"task": "tsk.one"}),
        lambda r: r["steps"]["1"].update(instruction="tsk.one"),
        lambda r: r["steps"]["1"].update(instructions=[ROLE, CONTEXT, TASK]),
        lambda r: r["steps"]["1"]["instructions"].update(task=TASK),
        lambda r: r["steps"]["1"]["instructions"].update(task=[ROLE]),
        lambda r: r["steps"]["1"]["instructions"].update(task=["tsk.one"]),
        lambda r: r["steps"]["1"]["instructions"].update(task=["spc_0000000000000000"]),
        lambda r: r["steps"]["1"].update(kind=r["steps"]["1"].pop("engine_kind")),
        lambda r: r["steps"]["1"].update(engine={"key": "chatgpt"}),
        lambda r: r["steps"]["1"].pop("engine"),
        lambda r: r["steps"]["1"].update(args=None),
        lambda r: r["steps"]["1"].update(args={"unexpected": True}),
        lambda r: r["steps"]["1"].update(model="absent"),
        lambda r: r["steps"]["1"].update(engine="absent"),
        lambda r: r.update(steps={}),
        lambda r: r.update(steps={"2": r["steps"]["1"]}),
        lambda r: r.update(steps=list(r["steps"].values())),
    ],
)
def test_nonconforming_plan_rejects_revision(control, mutate):
    record = _record()
    mutate(record)
    (control / "plans/one.json").write_text(json.dumps(record))
    _commit(control)
    with pytest.raises((ValueError, TypeError)):
        load_plan("plan.one")


@pytest.mark.parametrize(
    "text",
    [
        _instruction(TASK).replace("identity:", "slug:"),
        _instruction(TASK).replace("title:", "label:"),
        _instruction(TASK).replace("description:", "summary:"),
        _instruction(TASK).replace('description: ""', "component: task"),
        _instruction(TASK).replace(
            'description: ""', 'description: ""\nrecord: instruction'
        ),
        _instruction(TASK).replace(
            'description: ""', 'description: ""\nidentity: ' + TASK
        ),
        _instruction(TASK, body="  \n"),
        _instruction(TASK).replace('description: ""', "description: [broken"),
    ],
)
def test_nonconforming_instruction_rejects_whole_revision(control, text):
    (control / "instructions/task.md").write_text(text)
    _commit(control)
    with pytest.raises(ValueError):
        load_plan("plan.one")


def test_rejects_moving_ref_for_instruction(control):
    with pytest.raises(ValueError, match="immutable commit"):
        repository.read_instruction(TASK, "master")


@pytest.mark.parametrize(
    "kind,field,registry",
    [("script", "script", "local_scripts"), ("rag", "rag_profile", "rag_profiles")],
)
def test_script_and_rag_capabilities_and_missing_references(
    control, kind, field, registry
):
    record = _record()
    step = record["steps"]["1"]
    step.pop("model")
    step.update(engine_kind=kind, engine="runner", **{field: "one"})
    schema = {
        "type": "object",
        "properties": {"count": {"type": "integer", "minimum": 1}},
        "required": ["count"],
        "additionalProperties": False,
    }
    record["capabilities"] = {
        "engines": {
            "runner": {"kind": kind, "step_fields": [field], "args_schema": schema}
        },
        "models": {},
        "local_scripts": {},
        "rag_profiles": {},
    }
    record["capabilities"][registry]["one"] = {"args_schema": schema}
    step["args"] = {"count": 2}
    path = control / "plans/one.json"
    path.write_text(json.dumps(record))
    _commit(control)
    assert load_plan("plan.one").plan.step_args(1) == {"count": 2}
    step["args"] = {"count": "2"}
    path.write_text(json.dumps(record))
    _commit(control)
    with pytest.raises(ValueError, match="invalid capability args"):
        load_plan("plan.one")
    step["args"] = {"count": 2}
    record["capabilities"][registry].clear()
    path.write_text(json.dumps(record))
    _commit(control)
    with pytest.raises(ValueError, match="missing .* reference"):
        load_plan("plan.one")


def test_bad_unselected_plan_rejects_revision(control):
    (control / "plans/unused.json").write_text('{"slug": "unused"}')
    _commit(control)
    with pytest.raises(ValueError):
        load_plan("plan.one")


def test_duplicate_json_fields_rejected(control):
    path = control / "plans/one.json"
    path.write_text(
        path.read_text().replace(
            '"slug": "plan.one"', '"slug": "plan.one", "slug": "other"'
        )
    )
    _commit(control)
    with pytest.raises(ValueError, match="duplicate field"):
        load_plan("plan.one")


def test_external_capability_schema_rejected(control):
    record = _record()
    record["capabilities"]["engines"]["chatgpt"]["args_schema"]["$ref"] = (
        "https://example.com/moving-schema"
    )
    (control / "plans/one.json").write_text(json.dumps(record))
    _commit(control)
    with pytest.raises(ValueError, match="local references"):
        load_plan("plan.one")


def test_snapshot_contains_one_revision_and_committed_capabilities(
    control, monkeypatch
):
    from asc.control.snapshot import build_control_snapshot
    from asc.control.list import list_control_identities

    revision = repository.control_revision()
    calls = []

    def resolve():
        calls.append(revision)
        return revision

    monkeypatch.setattr(repository, "control_revision", resolve)
    snapshot = build_control_snapshot()
    assert calls == [revision]
    assert snapshot["source"]["revision"] == revision
    assert snapshot["registries"]["engines"] == _record()["capabilities"]["engines"]
    assert snapshot["registries"]["instructions"][TASK]["repo_commit"] == revision
    assert list_control_identities() == sorted([TASK, ROLE, CONTEXT, "plan.one"])


def test_conflicting_capability_metadata_rejects_revision(control):
    other = _record()
    other["slug"] = "other"
    other["capabilities"]["engines"]["chatgpt"]["title"] = "Conflicting declaration"
    (control / "plans/other.json").write_text(json.dumps(other))
    _commit(control)
    with pytest.raises(ValueError, match="conflicting capability"):
        load_plan("plan.one")


def test_instruction_symlink_is_rejected(control):
    (control / "instructions/link.md").symlink_to("task.md")
    _commit(control)
    with pytest.raises(ValueError, match="ordinary files"):
        load_plan("plan.one")


def test_enqueue_service_forwards_loaded_revision(monkeypatch):
    from types import SimpleNamespace
    from asc.enqueue import service

    seen = {}

    def materialize(**kwargs):
        seen.update(kwargs)
        return ()

    monkeypatch.setattr(service, "materialize_runtimes", materialize)
    monkeypatch.setattr(
        service,
        "create_job",
        lambda **kwargs: SimpleNamespace(raw_key="job:call:record"),
    )
    monkeypatch.setattr(service, "activate_job", lambda job: None)
    call = SimpleNamespace(identity="call", redis_key=SimpleNamespace(identity="call"))
    plan = SimpleNamespace(identity="plan.one")
    record = SimpleNamespace(
        call=call,
        call_key="call:call:record",
        directive=None,
        plan=SimpleNamespace(
            plan=plan, revision="a" * 40, step_count=1, plan_key="git-ref"
        ),
        source_identity="document.slug",
    )
    service.enqueue_record(record)
    assert seen["control_revision"] == "a" * 40
    assert seen["plan"] is plan


def test_instruction_body_preserves_committed_line_endings(control):
    path = control / "instructions/task.md"
    body = "  Keep spaces.\r\n\r\n"
    path.write_bytes(_instruction(TASK, body=body).encode("utf-8"))
    revision = _commit(control)
    assert repository.read_instruction(TASK, revision).content == body


def test_incompatible_extra_capability_reference_rejected(control):
    record = _record()
    record["steps"]["1"]["script"] = "absent"
    record["capabilities"]["engines"]["chatgpt"]["step_fields"].append("script")
    (control / "plans/one.json").write_text(json.dumps(record))
    _commit(control)
    with pytest.raises(ValueError, match="only its engine kind"):
        load_plan("plan.one")
