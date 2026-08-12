from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from .state import VaultState


def log_path(repo: Path, date: str | None = None) -> Path:
    stamp = date or datetime.now().astimezone().date().isoformat()
    return VaultState.for_vault(repo).root / "logs" / f"{stamp}.log"


def write_log(repo: Path, command: str, message: str, *, level: str = "INFO") -> None:
    path = log_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    text = str(message or "").rstrip() or "(no detail)"
    lines = text.splitlines() or [text]
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{timestamp} {level:<5} {command}: {lines[0]}\n")
        for line in lines[1:]:
            handle.write(f"{' ' * 32}{line}\n")


def read_log(repo: Path, *, date: str | None = None, lines: int = 200) -> str:
    path = log_path(repo, date)
    if not path.is_file():
        return f"No feeder log for {path.stem}.\n"
    rows = path.read_text(encoding="utf-8").splitlines()
    if lines > 0:
        rows = rows[-lines:]
    return "\n".join(rows) + ("\n" if rows else "")


def summarize_items(items: Iterable[dict]) -> str:
    rendered: list[str] = []
    for item in items:
        identity = item.get("record_identity") or item.get("slug") or item.get("prompt_slug") or "?"
        branch = item.get("branch") or item.get("transport_branch") or ""
        path = item.get("source_path") or item.get("path") or ""
        detail = " ".join(part for part in (str(identity), str(branch), str(path)) if part)
        rendered.append(detail)
    return "\n".join(rendered)
