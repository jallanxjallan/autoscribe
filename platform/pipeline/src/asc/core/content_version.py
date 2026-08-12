"""Deterministic identities for immutable uploaded control assets."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def _digest(slug: str, payload: bytes) -> str:
    clean_slug = str(slug).strip()
    if not clean_slug:
        raise ValueError("versioned asset slug must be non-empty")
    hasher = hashlib.sha256()
    hasher.update(clean_slug.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(payload)
    return hasher.hexdigest()


def plan_version_identity(slug: str, content: Mapping[str, Any]) -> str:
    """Return a stable SHA-256 identity for one exact plan payload."""

    canonical = json.dumps(
        dict(content),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _digest(slug, canonical)


def instruction_version_identity(slug: str, content: str) -> str:
    """Return a stable SHA-256 identity for one exact instruction body."""

    if not isinstance(content, str) or not content.strip():
        raise ValueError("instruction content must be a non-empty string")
    return _digest(slug, content.strip().encode("utf-8"))


__all__ = ["instruction_version_identity", "plan_version_identity"]
