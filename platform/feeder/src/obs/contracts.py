from __future__ import annotations

import re
from pathlib import Path
from secrets import token_hex
from typing import Any

from .errors import ObsError


def upload_record(*, type: str, identity: str, content: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    record_type = str(type or "").strip()
    slug = str(identity or "").strip()
    if not record_type:
        raise ObsError("upload record requires type")
    if not slug:
        raise ObsError("upload record requires identity")
    if not isinstance(extra or {}, dict):
        raise ObsError(f"{slug}: upload extra must be an object")
    return {"type": record_type, "identity": slug, "content": content, "extra": dict(extra or {})}


def enqueue_record(*, call: str, plan: str, directive: str | None = None) -> dict[str, str]:
    call_slug = str(call or "").strip()
    plan_slug = str(plan or "").strip()
    if not call_slug or not plan_slug:
        raise ObsError("enqueue manifest requires call and plan slugs")
    record = {"call": call_slug, "plan": plan_slug}
    if directive is not None:
        if not isinstance(directive, str):
            raise ObsError("enqueue manifest directive must be a string or null")
        clean_directive = directive.strip()
        if clean_directive:
            record["directive"] = clean_directive
    return record


def provisional_slug(filename_hint: str) -> str:
    stem = Path(str(filename_hint or "untitled")).stem.lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-") or "untitled"
    return f"prv.{stem}.{token_hex(3)}"
