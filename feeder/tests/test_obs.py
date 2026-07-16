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
    assert output.split(b"\0") == [
        b"--metadata=record_plan:plan.test",
        str(source.resolve()).encode(),
        b"",
    ]
    subject = subprocess.run(
        ["git", "log", "-1", "--format=%s"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    assert subject.startswith("plan.test ")
