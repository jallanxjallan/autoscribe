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
