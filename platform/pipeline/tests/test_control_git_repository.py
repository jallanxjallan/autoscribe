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
from asc import extensions
from asc.enqueue import reader, service

ROLE = "rol_4Q7M2V9K8D3R6X1P"
CONTEXT = "ctx_8J2F6R4W9P1C7T5N"
TASK = "tsk_3N6K8R2V7M4Q9D1X"


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
    (repo / "plans/plan.one.json").write_text(json.dumps(_record()))
    _commit(repo)
    monkeypatch.setattr(
        repository, "CONTROL", ControlRepoConfig(repo, "master", "Tests", "tests@local")
    )
    extension_root = tmp_path / "extensions"
    (extension_root / "engines").mkdir(parents=True)
    (extension_root / "engines/chatgpt.py").write_text(
        "def make_call(value): return value\n"
    )
    monkeypatch.setattr(extensions, "EXTENSIONS_ROOT", extension_root)
    return repo


def test_bare_repository_reads_and_blob_version(control, tmp_path, monkeypatch):
    bare = tmp_path / "control.git"
    _git(control, "clone", "--bare", str(control), str(bare))
    monkeypatch.setattr(
        repository, "CONTROL", ControlRepoConfig(bare, "master", "Tests", "tests@local")
    )
    revision = repository.control_revision()
    view = repository.ControlRepository.at_revision(revision)
    plan = view.read_plan("plan.one")
    instruction = view.read_instruction(TASK)
    assert plan.revision == instruction.revision == revision
    assert plan.path == "plans/plan.one.json"
    assert instruction.path == "instructions/task.md"
    assert instruction.fingerprint == _git(
        bare, "rev-parse", f"{revision}:instructions/task.md"
    )
    assert instruction.extra["repo_commit"] == revision
    assert view.read_instruction(TASK) is instruction
    assert view.read_plan("plan.one") is plan


def test_one_revision_per_enqueue_with_branch_advance(control, monkeypatch):
    from io import StringIO
    from types import SimpleNamespace

    original = repository.ControlRepository.read_plan
    resolutions, sources, writes = [], [], []
    revision = repository.control_revision()
    resolve = repository.control_revision
    monkeypatch.setattr(
        repository, "control_revision", lambda: resolutions.append(True) or resolve()
    )

    def load_then_advance(view, slug):
        plan = original(view, slug)
        (control / "instructions/task.md").write_text(
            _instruction(TASK, body="Changed at B.\n")
        )
        changed = _record()
        changed["capabilities"]["models"].clear()
        (control / "plans/plan.one.json").write_text(json.dumps(changed))
        _commit(control)
        return plan

    monkeypatch.setattr(repository.ControlRepository, "read_plan", load_then_advance)
    call = SimpleNamespace(
        identity="call",
        source_identity="document",
        redis_key=SimpleNamespace(identity="call"),
    )
    monkeypatch.setattr(reader, "store_call", lambda raw: ("call:call:record", call))

    def materialize(identity, *, control_revision, source):
        assert control_revision == source.revision == revision
        sources.append(source)
        return f"instruction:{identity}:record"

    monkeypatch.setattr(runtime, "resolve_instruction_key", materialize)
    monkeypatch.setattr(runtime.Runtime, "save", lambda self, **kw: writes.append(self))
    monkeypatch.setattr(
        service, "create_job", lambda **kw: SimpleNamespace(raw_key="job:call:record")
    )
    monkeypatch.setattr(service, "activate_job", lambda job: None)
    report = service.enqueue_from_stream(
        StringIO('{"identity":"document","plan":"plan.one","content":"text"}\n')
    )
    assert len(report.records) == 1
    assert resolutions == [True]
    assert sources[-1].content == "Do the thing.\n"
    assert writes[0].model == "cheap"
    assert repository.read_instruction(TASK, revision).content == "Do the thing.\n"
    assert repository.read_instruction(TASK, resolve()).content == "Changed at B.\n"


def test_filename_and_title_are_nonsemantic(control):
    old = repository.read_instruction(TASK, repository.control_revision())
    (control / "instructions/task.md").rename(control / "instructions/unrelated.md")
    (control / "instructions/unrelated.md").write_text(
        _instruction(TASK, title="Renamed")
    )
    new = repository.read_instruction(TASK, _commit(control))
    assert new.identity == old.identity
    assert new.title == "Renamed"
    assert new.fingerprint != old.fingerprint


@pytest.mark.parametrize(
    "component,name", [("plan", "absent"), ("instruction", "tsk_0000000000000000")]
)
def test_missing_record_has_revision(control, component, name):
    revision = repository.control_revision()
    with pytest.raises(KeyError) as error:
        if component == "plan":
            repository.read_plan(name, revision)
        else:
            repository.read_instruction(name, revision)
    assert (
        error.value.args[0]
        == f"missing {component}: {name} at Control revision {revision}"
    )


@pytest.mark.parametrize(
    "field,registry,label",
    [
        ("engine", "engines", "engine"),
        ("model", "models", "model"),
        ("script", "local_scripts", "local script"),
        ("rag_profile", "rag_profiles", "RAG profile"),
    ],
)
def test_missing_component_before_call_creation(
    control, monkeypatch, field, registry, label
):
    from io import StringIO

    record = _record()
    record["steps"]["1"][field] = "absent"
    (control / "plans/plan.one.json").write_text(json.dumps(record))
    revision = _commit(control)
    monkeypatch.setattr(
        reader,
        "store_call",
        lambda raw: pytest.fail("call created before availability check"),
    )
    with pytest.raises(KeyError) as error:
        list(reader.iter_enqueue_records(StringIO('{"plan":"plan.one"}\n')))
    assert (
        error.value.args[0] == f"missing {label}: absent at Control revision {revision}"
    )


@pytest.mark.parametrize("missing", ["plan", "instruction"])
def test_missing_source_before_call_creation(control, monkeypatch, missing):
    from io import StringIO

    if missing == "instruction":
        (control / "instructions/task.md").unlink()
        _commit(control)
    slug = "absent" if missing == "plan" else "plan.one"
    monkeypatch.setattr(reader, "store_call", lambda raw: pytest.fail("call created"))
    with pytest.raises(
        KeyError, match=f"missing {missing}: " + (slug if missing == "plan" else TASK)
    ):
        list(reader.iter_enqueue_records(StringIO(json.dumps({"plan": slug}) + "\n")))


@pytest.mark.parametrize(
    "kind,field,registry,label",
    [
        ("script", "script", "local_scripts", "local script"),
        ("rag", "rag_profile", "rag_profiles", "RAG profile"),
    ],
)
def test_external_artifact_availability(control, kind, field, registry, label):
    record = _record()
    step = record["steps"]["1"]
    step.pop("model")
    step.update(engine_kind=kind, **{field: "one"})
    record["capabilities"][registry]["one"] = {"path": "rag_profiles/one.txt"}
    (control / "plans/plan.one.json").write_text(json.dumps(record))
    _commit(control)
    with pytest.raises(FileNotFoundError, match=f"missing {label}: one"):
        load_plan("plan.one")
    path = extensions.EXTENSIONS_ROOT / (
        "scripts/one.py" if kind == "script" else "rag_profiles/one.txt"
    )
    path.parent.mkdir()
    path.write_text("available")
    assert load_plan("plan.one").plan.steps["1"][field] == "one"


def test_engine_execution_artifact_required(control):
    (extensions.EXTENSIONS_ROOT / "engines/chatgpt.py").unlink()
    with pytest.raises(FileNotFoundError, match="missing engine: chatgpt"):
        load_plan("plan.one")


def test_unrelated_records_are_not_parsed_or_enumerated(control, monkeypatch):
    selected = _record()
    selected["steps"]["2"] = selected["steps"]["1"]
    (control / "plans/plan.one.json").write_text(json.dumps(selected))
    (control / "plans/unused.json").write_text('{"slug":"unused", broken')
    (control / "instructions/unused.md").write_text(
        "---\nidentity: tsk_0000000000000000\ntitle: [broken\n---\n"
    )
    _commit(control)
    calls = []
    original = repository._git

    def spy(repo, *args, **kwargs):
        calls.append(args)
        return original(repo, *args, **kwargs)

    monkeypatch.setattr(repository, "_git", spy)
    monkeypatch.setattr(
        repository, "list_revision", lambda *a: pytest.fail("whole listing")
    )
    loaded = load_plan("plan.one")
    assert set(loaded.instructions) == {ROLE, CONTEXT, TASK}
    assert len([args for args in calls if args[0] == "show"]) == 4
    assert all(
        len(args) == 5 and args[-1].endswith((".md", ".json"))
        for args in calls
        if args[0] == "ls-tree"
    )


def test_authoring_semantics_are_not_validated(control, monkeypatch):
    record = _record()
    step = record["steps"]["1"]
    step.update(temperature=99, max_output_tokens=-5, args={"unexpected": True})
    record["capabilities"]["engines"]["chatgpt"] = {
        "kind": "different",
        "args_schema": {"$ref": "https://example.com/schema"},
    }
    record["capabilities"]["models"]["cheap"]["engine"] = "different"
    (control / "plans/plan.one.json").write_text(json.dumps(record))
    (control / "instructions/task.md").write_text(
        _instruction(TASK, body="").replace(
            'description: ""', 'description: ""\nextra: metadata'
        )
    )
    _commit(control)
    loaded = load_plan("plan.one")
    monkeypatch.setattr(
        runtime, "resolve_instruction_key", lambda *a, **kw: "instruction:one:record"
    )
    monkeypatch.setattr(runtime.Runtime, "save", lambda self, **kw: self.raw_key)
    result = runtime.materialize_runtimes(
        call_identity="call",
        plan=loaded.plan,
        control_revision=loaded.revision,
        instruction_sources=loaded.instructions,
    )
    assert result[0].temperature == 99
    assert result[0].max_output_tokens == -5
    assert result[0].args == {"unexpected": True}


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(record_identity=r.pop("slug")),
        lambda r: r["steps"]["1"].update(
            instruction=r["steps"]["1"].pop("instructions")
        ),
        lambda r: r["steps"]["1"].update(engine={"key": "chatgpt"}),
        lambda r: r["steps"]["1"].update(kind=r["steps"]["1"].pop("engine_kind")),
        lambda r: r["steps"]["1"]["instructions"].update(task=TASK),
    ],
)
def test_legacy_forms_are_not_normalized(control, change):
    record = _record()
    change(record)
    (control / "plans/plan.one.json").write_text(json.dumps(record))
    _commit(control)
    with pytest.raises((KeyError, TypeError, AttributeError)):
        load_plan("plan.one")


@pytest.mark.parametrize(
    "path,text,message",
    [
        ("plans/plan.one.json", '{"slug":"plan.one", broken', "cannot parse canonical JSON"),
        (
            "instructions/task.md",
            "---\nidentity: " + TASK + "\ntitle: [broken\n---\n",
            "cannot parse canonical YAML",
        ),
    ],
)
def test_unparseable_selected_source(control, path, text, message):
    (control / path).write_text(text)
    _commit(control)
    with pytest.raises(ValueError, match=message):
        load_plan("plan.one")


def test_rejects_moving_or_noncommit_revision(control):
    with pytest.raises(ValueError, match="immutable commit"):
        repository.read_instruction(TASK, "master")
    oid = _git(control, "rev-parse", "HEAD:instructions/task.md")
    with pytest.raises(RuntimeError):
        repository.read_instruction(TASK, oid)


def test_unavailable_repository_and_ref(control, monkeypatch):
    monkeypatch.setattr(
        repository,
        "CONTROL",
        ControlRepoConfig(control, "absent", "Tests", "tests@local"),
    )
    with pytest.raises(RuntimeError):
        repository.control_revision()
    monkeypatch.setattr(
        repository,
        "CONTROL",
        ControlRepoConfig(control / "absent", "master", "Tests", "tests@local"),
    )
    with pytest.raises(FileNotFoundError):
        repository.control_revision()


def test_instruction_body_preserves_committed_line_endings(control):
    body = "  Keep spaces.\r\n\r\n"
    (control / "instructions/task.md").write_bytes(
        _instruction(TASK, body=body).encode()
    )
    assert repository.read_instruction(TASK, _commit(control)).content == body


def test_snapshot_and_listing_are_separate_administrative_apis(control):
    from asc.control.snapshot import build_control_snapshot
    from asc.control.list import list_control_identities

    snapshot = build_control_snapshot()
    assert snapshot["source"]["revision"] == repository.control_revision()
    assert snapshot["registries"]["engines"] == _record()["capabilities"]["engines"]
    assert list_control_identities() == sorted([TASK, ROLE, CONTEXT, "plan.one"])


def test_wrapped_plan_and_revision_lookup(control, monkeypatch):
    identity = "plan.hhp-pro-bono-position-paper-boxout.4h8n3d"
    before = repository.control_revision()
    record = {"record_type": "plan", "record_identity": identity,
              "record_content": {"label": "Boxout", "description": "", "steps": {}}}
    path = control / f"plans/{identity}.json"
    path.write_text(json.dumps(record))
    revision = _commit(control)
    def no_search(*args):
        pytest.fail("plan lookup searched content")
    monkeypatch.setattr(repository.ControlRepository, "_find", no_search)
    assert repository.read_plan(identity, revision).plan.identity == identity
    with pytest.raises(KeyError, match="missing plan"):
        repository.read_plan(identity, before)
    path.write_text("{broken")
    with pytest.raises(ValueError, match="cannot parse canonical JSON"):
        repository.read_plan(identity, _commit(control))
    record["record_identity"] = "plan.other"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="identity mismatch"):
        repository.read_plan(identity, _commit(control))
    record["record_content"].pop("steps")
    path.write_text(json.dumps(record))
    with pytest.raises(KeyError) as error:
        repository.read_plan(identity, _commit(control))
    assert "missing plan" not in str(error.value)


def test_task_prefix_specification():
    from asc.models.control.plan import instruction_scope
    assert instruction_scope(TASK) == "task"
    with pytest.raises(ValueError, match="invalid instruction identity"):
        instruction_scope(TASK.replace("tsk_", "spc_"))


def test_published_instruction_frontmatter(control):
    identity = "tsk.prepare-pro-bono-position-paper-boxout.4h8n3d"
    (control / "instructions/task.md").write_text(
        f"---\ntitle: Boxout\nslug: {identity}\ntype: instruction\nscope: task\n---\nBody\n"
    )
    source = repository.read_instruction(identity, _commit(control))
    assert source.identity == identity
    assert source.extra["scope"] == "task"
    assert source.content == "Body\n"


def test_instruction_identity_mismatch(control):
    (control / "instructions/task.md").write_text(
        _instruction(TASK) + f"identity: {ROLE}\n"
    )
    (control / "instructions/role.md").unlink()
    with pytest.raises(ValueError, match="identity mismatch"):
        repository.read_instruction(ROLE, _commit(control))
