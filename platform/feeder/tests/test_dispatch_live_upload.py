from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml


SAMPLE_CLIPBOARD = Path(__file__).with_name("data.txt")


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.fail(
            f"{name} is required for the live upload test. "
            "This test performs a real dispatch, commit, upload, and inflight tag."
        )
    return value


def _clipboard_titles(path: Path) -> list[str]:
    if not path.is_file():
        pytest.fail(f"clipboard fixture not found: {path}")
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) < 2:
        pytest.fail(f"clipboard fixture contains no data rows: {path}")
    header = lines[0].split("\t")
    try:
        title_index = header.index("file name")
    except ValueError:
        pytest.fail(f"clipboard fixture has no 'file name' column: {path}")
    return [columns[title_index].strip() for line in lines[1:] if (columns := line.split("\t"))]


def _frontmatter_slug(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return ""
    try:
        _, frontmatter, _ = text.split("---", 2)
        parsed = yaml.safe_load(frontmatter) or {}
    except (ValueError, yaml.YAMLError):
        return ""
    return str(parsed.get("slug") or "").strip() if isinstance(parsed, dict) else ""


def _resolve_titles(vault: Path, titles: list[str]) -> list[str]:
    markdown = list(vault.rglob("*.md"))
    resolved: list[str] = []
    errors: list[str] = []
    for title in titles:
        matches = [path for path in markdown if path.stem == title]
        if not matches:
            errors.append(f"not found: {title}")
            continue
        if len(matches) > 1:
            errors.append(
                f"ambiguous: {title}: "
                + ", ".join(path.relative_to(vault).as_posix() for path in matches)
            )
            continue
        path = matches[0]
        slug = _frontmatter_slug(path)
        if not slug:
            errors.append(f"missing slug: {path.relative_to(vault).as_posix()}")
            continue
        resolved.append(path.relative_to(vault).as_posix())
    if errors:
        pytest.fail("clipboard resolution failed:\n  " + "\n  ".join(errors))
    return resolved


def _run_ipc(vault: Path, request: dict[str, Any]) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    command = [sys.executable, "-m", "obs.cli", "--vault", str(vault), "ipc"]
    completed = subprocess.run(
        command,
        input=json.dumps(request, ensure_ascii=False),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
        check=False,
    )
    try:
        response = json.loads(completed.stdout)
    except json.JSONDecodeError:
        pytest.fail(
            "obs IPC did not return JSON\n"
            f"command: {' '.join(command)}\n"
            f"exit status: {completed.returncode}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return completed, response


def _git(vault: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(vault), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        pytest.fail(
            f"git {' '.join(args)} failed ({completed.returncode})\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return completed.stdout.strip()


@pytest.mark.live_upload
def test_dispatch_run_performs_real_upload() -> None:
    """Exercise the same JSON IPC boundary as Dispatch Run, including enqueue.

    Required environment:
      AUTOSCRIBE_LIVE_VAULT: active Git-backed Obsidian vault
      AUTOSCRIBE_LIVE_PLAN: existing remote plan slug

    Optional environment:
      AUTOSCRIBE_LIVE_CLIPBOARD: tab-delimited clipboard fixture; defaults to
        tests/data.txt included with this test.

    This intentionally creates a real source commit, calls ``autoscribe
    enqueue``, and adds an inflight tag only after enqueue exits successfully.
    """
    if os.environ.get("AUTOSCRIBE_LIVE_UPLOAD", "").strip() != "1":
        pytest.skip("set AUTOSCRIBE_LIVE_UPLOAD=1 to enable the real upload test")

    vault = Path(_required_env("AUTOSCRIBE_LIVE_VAULT")).expanduser().resolve()
    plan_slug = _required_env("AUTOSCRIBE_LIVE_PLAN")
    clipboard = Path(os.environ.get("AUTOSCRIBE_LIVE_CLIPBOARD", SAMPLE_CLIPBOARD)).expanduser().resolve()

    if not (vault / ".git").exists():
        pytest.fail(f"AUTOSCRIBE_LIVE_VAULT is not a Git working tree: {vault}")

    paths = _resolve_titles(vault, _clipboard_titles(clipboard))
    before_head = _git(vault, "rev-parse", "HEAD")
    message = f"PYTEST LIVE DISPATCH {plan_slug}: {datetime.now().astimezone().isoformat(timespec='seconds')}"
    request = {
        "operation": "dispatch.run",
        "paths": paths,
        "plan_slug": plan_slug,
        "message": message,
        "dry_run": False,
    }

    completed, response = _run_ipc(vault, request)

    diagnostic = json.dumps(response, ensure_ascii=False, indent=2)
    assert completed.returncode == 0, (
        f"obs IPC process failed\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    assert response.get("ok") is True, (
        "Dispatch Run reached feeder but the live upload failed.\n"
        f"IPC response:\n{diagnostic}\n"
        f"stderr:\n{completed.stderr}"
    )

    result = response.get("result") or {}
    assert result.get("dry_run") is False, diagnostic
    assert result.get("count") == len(paths), diagnostic
    assert result.get("failed_count") == 0, diagnostic
    assert result.get("commit"), diagnostic
    assert result.get("tag", {}).get("name"), diagnostic

    commit = str(result["commit"])
    tag = str(result["tag"]["name"])
    assert commit != before_head, diagnostic
    assert _git(vault, "rev-parse", "HEAD") == commit
    assert _git(vault, "rev-list", "-n", "1", tag) == commit
    assert _git(vault, "show", "-s", "--format=%s", commit) == message

    dispatched_paths = [str(item.get("path")) for item in result.get("items", [])]
    assert dispatched_paths == paths, diagnostic
