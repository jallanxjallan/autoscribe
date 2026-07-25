import hashlib
from pathlib import Path

from obs.markdown import parse_markdown, render_markdown
from obs.state import VaultState, vault_key
from obs.vault import Vault


def test_markdown_round_trip():
    source = "---\nslug: cnt.test.abc123\nstatus: draft\n---\nHello\n"
    doc = parse_markdown(source)
    doc.frontmatter["status"] = "ai-generated"
    rendered = render_markdown(doc.frontmatter, doc.body)
    assert "status: ai-generated" in rendered
    assert rendered.endswith("Hello\n")


def test_vault_scan(tmp_path: Path):
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / "_control").mkdir()
    (tmp_path / "Scenes").mkdir()
    (tmp_path / "Scenes" / "One.md").write_text(
        "---\nslug: cnt.one.abc123\ntitle: One\n---\nText\n", encoding="utf-8"
    )
    records = Vault(tmp_path).records()
    assert [(record.slug, record.path) for record in records] == [("cnt.one.abc123", "Scenes/One.md")]


def test_state_matches_control_vault_key(tmp_path: Path, monkeypatch):
    vault = (tmp_path / "My Vault").resolve()
    vault.mkdir()
    data = tmp_path / "share" / "autoscribe"
    monkeypatch.setenv("AUTOSCRIBE_HOME", str(data))
    digest = hashlib.sha1(str(vault).encode("utf-8")).hexdigest()[:8]
    expected_key = f"my-vault-{digest}"
    state = VaultState.for_vault(vault)
    assert vault_key(vault) == expected_key
    assert state.root == data / "obsidian" / "vaults" / expected_key
    assert state.current_run == state.root / "workflow" / "runs" / "current-run.json"
    assert state.writing("writeback") == state.root / "writeback" / "writeback-results.json"


def test_autoscribe_bin_prefers_interpreter_sibling(tmp_path: Path, monkeypatch):
    import obs.executables as executables

    python = tmp_path / "bin" / "python"
    asc = tmp_path / "bin" / "asc"
    python.parent.mkdir()
    python.write_text("", encoding="utf-8")
    asc.write_text("#!/bin/sh\n", encoding="utf-8")
    asc.chmod(0o755)
    monkeypatch.delenv("AUTOSCRIBE_BIN", raising=False)
    monkeypatch.delenv("ASC_BIN", raising=False)
    monkeypatch.setattr(executables.sys, "executable", str(python))
    monkeypatch.setattr(executables.shutil, "which", lambda _: None)

    assert executables.autoscribe_bin() == str(asc.resolve())


def test_user_commits_exclude_autoscribe_commits(tmp_path: Path):
    import subprocess
    from obs import git

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    (tmp_path / "one.md").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "one.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "Editorial pass"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "one.md").write_text("two\n", encoding="utf-8")
    subprocess.run(["git", "add", "one.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "UPLOAD instructions: 20260715"], cwd=tmp_path, check=True, capture_output=True)

    commits = git.user_commits(tmp_path)
    assert [commit["subject"] for commit in commits] == ["Editorial pass"]
    assert commits[0]["files"] == ["one.md"]


def test_dispatch_run_emits_nul_pandoc_arguments_and_commits(tmp_path: Path):
    import json
    import subprocess
    from obs.uploads import dispatch_run

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    source = tmp_path / "One File.md"
    source.write_text("---\nslug: cnt.one\n---\nText\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True, capture_output=True)

    manifest = tmp_path / "run.json"
    manifest.write_text(json.dumps({
        "vault": {"root": str(tmp_path)},
        "plan_slug": "plan.test",
        "items": [{"path": "One File.md", "prompt_slug": "cnt.one"}],
    }), encoding="utf-8")

    items, output = dispatch_run(tmp_path, manifest_path=manifest)
    assert items[0]["absolute_path"] == str(source.resolve())
    records = [json.loads(line) for line in output.decode().splitlines()]
    assert records == [{
        "record_identity": "cnt.one",
        "record_type": "content",
        "record_plan": "plan.test",
        "record_content": "---\nslug: cnt.one\n---\nText\n",
    }]
    subject = subprocess.run(
        ["git", "log", "-1", "--format=%s"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert subject.startswith("plan.test ")


def test_save_plan_emits_payload_object(tmp_path: Path, monkeypatch):
    import json
    from types import SimpleNamespace
    import obs.plans as plans

    captured = {}
    monkeypatch.setattr(plans, "sync_instructions", lambda cwd, sets: [])
    monkeypatch.setattr(plans, "autoscribe_bin", lambda: "/fake/asc")

    def fake_run(command, *, cwd, input_text):
        captured["command"] = command
        captured["input_text"] = input_text
        return SimpleNamespace(stdout="ok\n")

    monkeypatch.setattr(plans, "run", fake_run)

    record = {
        "record_type": "plan",
        "record_identity": "plan.test.abc123",
        "payload": {
            "label": "Test",
            "description": "Human-readable description",
            "steps": {
                "1": {
                    "engine": "chatgpt",
                    "instruction_slugs": {
                        "role": "ins.role.abc123",
                        "context": "ins.context.abc123",
                        "instructions": "ins.task.abc123",
                    },
                }
            },
        },
    }

    result = plans.save_plan(record, cwd=tmp_path)
    envelope = json.loads(captured["input_text"])

    assert envelope == record
    assert isinstance(envelope["payload"], dict)
    assert result["pipeline_output"] == "ok"


def test_load_plan_materializes_persisted_fields(monkeypatch):
    import json
    import obs.plans as plans

    stored = {
        "record_type": "plan",
        "record_identity": "plan.test.abc123",
        "slug": "plan.test.abc123",
        "ttl": 3600,
        "metadata_json": json.dumps({
            "label": "Test plan",
            "description": "Loaded from Redis",
        }),
        "steps_json": json.dumps({
            "1": {
                "engine": "chatgpt",
                "instruction_slugs": {"instructions": "ins.task.abc123"},
            }
        }),
    }
    monkeypatch.setattr(plans, "list_plans", lambda: [stored])

    loaded = plans.load_plan("plan.test.abc123")

    assert loaded["record_identity"] == "plan.test.abc123"
    assert loaded["ttl"] == 3600
    assert loaded["label"] == "Test plan"
    assert loaded["description"] == "Loaded from Redis"
    assert loaded["steps"]["1"]["engine"] == "chatgpt"



def test_dispatch_paths_does_not_infer_inflight_from_shared_plan_commit(tmp_path: Path, monkeypatch):
    import json
    import subprocess
    from types import SimpleNamespace
    from obs import uploads
    from obs import executables

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)

    paths = []
    for ordinal in range(1, 4):
        relpath = f"File {ordinal}.md"
        paths.append(relpath)
        (tmp_path / relpath).write_text(
            f"---\nslug: cnt.file-{ordinal}\n---\nText {ordinal}\n",
            encoding="utf-8",
        )

    subprocess.run(["git", "add", "--", *paths], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "commit", "-m", "plan.shared 2026-07-22 12:00:00 +0700"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    captured = {}
    monkeypatch.setattr(uploads.git, "commit_files", lambda repo, selected, message: "dispatch-commit")
    monkeypatch.setattr(uploads.git, "tag_inflight", lambda repo, commit, plan, stamp: f"inflight/{plan}/stamp")
    monkeypatch.setattr(executables, "autoscribe_bin", lambda: "/fake/asc")

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs["input"]
        return SimpleNamespace(returncode=0, stdout=b"queued 3\n", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = uploads.dispatch_paths(
        tmp_path,
        paths=paths,
        plan_slug="plan.shared",
    )

    records = [json.loads(line) for line in captured["input"].decode().splitlines()]
    assert result["count"] == 3
    assert result["failed_count"] == 0
    assert [record["record_identity"] for record in records] == [
        "cnt.file-1",
        "cnt.file-2",
        "cnt.file-3",
    ]


def test_dispatch_paths_commits_selection_with_optional_message_and_tags(tmp_path: Path, monkeypatch):
    import json
    import subprocess
    from types import SimpleNamespace
    from obs import uploads
    from obs import executables

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    source = tmp_path / "Selected.md"
    source.write_text("---\nslug: cnt.selected\n---\nText\n", encoding="utf-8")
    subprocess.run(["git", "add", "Selected.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial"], cwd=tmp_path, check=True, capture_output=True)

    monkeypatch.setattr(executables, "autoscribe_bin", lambda: "/fake/asc")
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs["input"]
        return SimpleNamespace(returncode=0, stdout=b"queued 1\n", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(uploads.git, "commit_files", lambda repo, paths, message: captured.setdefault("commit", (paths, message)) and "abc123")
    monkeypatch.setattr(uploads.git, "tag_inflight", lambda repo, commit, plan, stamp: captured.setdefault("tag", (commit, plan, stamp)) and f"inflight/{plan}/stamp")

    result = uploads.dispatch_paths(
        tmp_path,
        paths=["Selected.md"],
        plan_slug="plan.cleanup",
        message="Cleanup selected chapter",
    )

    assert captured["commit"] == (["Selected.md"], "Cleanup selected chapter")
    assert captured["tag"][0:2] == ("abc123", "plan.cleanup")
    records = [json.loads(line) for line in captured["input"].decode().splitlines()]
    assert records[0]["record_identity"] == "cnt.selected"
    assert result["commit"] == "abc123"
    assert result["tag"]["name"].startswith("inflight/plan.cleanup/")


def test_dispatch_paths_uses_generated_message_when_blank(tmp_path: Path, monkeypatch):
    import subprocess
    from types import SimpleNamespace
    from obs import uploads
    from obs import executables

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    source = tmp_path / "Selected.md"
    source.write_text("---\nslug: cnt.selected\n---\nText\n", encoding="utf-8")

    captured = {}
    monkeypatch.setattr(executables, "autoscribe_bin", lambda: "/fake/asc")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=b"ok\n", stderr=b""))
    monkeypatch.setattr(uploads.git, "commit_files", lambda repo, paths, message: captured.setdefault("message", message) and "abc123")
    monkeypatch.setattr(uploads.git, "tag_inflight", lambda *args: "inflight/plan.cleanup/stamp")

    result = uploads.dispatch_paths(tmp_path, paths=["Selected.md"], plan_slug="plan.cleanup")
    assert captured["message"].startswith("DISPATCH plan.cleanup:")
    assert result["message"] == captured["message"]
