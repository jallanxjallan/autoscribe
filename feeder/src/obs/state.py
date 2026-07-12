from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path


def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "vault"


def vault_key(root: Path | str) -> str:
    """Return the vault identity used by the Obsidian control layer."""
    vault = Path(root).expanduser().resolve()
    digest = hashlib.sha1(str(vault).encode("utf-8")).hexdigest()[:8]
    return f"{_safe_name(vault.name)}-{digest}"


def data_root() -> Path:
    """Return the shared AutoScribe data root."""
    configured = os.environ.get("AUTOSCRIBE_HOME") or os.environ.get("AUTOSCRIBE_DATA_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    return (base / "autoscribe").resolve()


@dataclass(frozen=True)
class VaultState:
    vault_root: Path
    root: Path

    @classmethod
    def for_vault(cls, vault_root: Path | str) -> "VaultState":
        vault = Path(vault_root).expanduser().resolve()
        root = data_root() / "obsidian" / "vaults" / vault_key(vault)
        return cls(vault_root=vault, root=root)

    def selection(self, operation: str) -> Path:
        filename = operation if operation.endswith(".json") else f"{operation}.json"
        return self.root / "selections" / filename

    @property
    def plans(self) -> Path:
        return self.root / "workflow" / "plans"

    @property
    def current_run(self) -> Path:
        return self.root / "workflow" / "runs" / "current-run.json"

    def writing(self, mode: str) -> Path:
        return self.root / mode / f"{mode}-results.json"
