from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from asc.registries.extensions import load_transform

ENGINE = "scripts"
ENGINE_COMPONENT = {
    "label": "Local script",
    "kind": "script",
    "step_fields": ["script", "args", "instructions", "ad_hoc"],
}

_CONTENT_FIELDS = ("record_content", "result_content", "content", "body", "text")


class FatalScriptError(RuntimeError):
    """Raised for local script failures; these are not retryable congestion."""


def _selector_key(value: object, field_name: str) -> str:
    """Normalize a UI selector/string into a registry component key."""
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, Mapping):
        raw = value.get("key") or value.get("slug") or value.get("name")
        text = str(raw).strip() if raw is not None else ""
    else:
        text = ""

    if not text:
        raise FatalScriptError(f"missing {field_name}")

    return text


def _script_component(value: object) -> str:
    """Return the importable local-script component expected by load_transform().

    Plan/UI data may carry a short script key such as ``insert_header`` or a
    selector dict. The registry loader validates import packages before import,
    so short keys must be expanded to the allowed ``scripts`` package here.
    """
    key = _selector_key(value, "script")

    if key.startswith("scripts."):
        return key

    if key.startswith("asc.scripts."):
        return key.removeprefix("asc.")

    return f"scripts.{key}"


def _loads_json(text: str) -> object | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _json_content_line(text: str) -> object | None:
    """Return a record-like JSON line embedded in transform-marked text.

    This handles bad intermediate values such as:

        <<<local-transform:insert-header>>>

        {"class":"article","record_content":"..."}
        []

        <<<local-transform:insert-footer>>>
    """
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("{") or not line.endswith("}"):
            continue
        obj = _loads_json(line)
        if isinstance(obj, Mapping) and any(field in obj for field in _CONTENT_FIELDS):
            return obj
    return None


def _record_content(value: object, *, depth: int = 0) -> str:
    """Extract the actual content string from pipeline records before scripts run.

    The worker may pass a full call/result record as JSON. Local scripts should
    transform the record payload, not the serialized wrapper. This recursively
    unwraps known content fields and JSON-stringified record payloads.
    """
    if depth > 8:
        return str(value)

    if isinstance(value, Mapping):
        for field in _CONTENT_FIELDS:
            if field in value:
                return _record_content(value[field], depth=depth + 1)
        return str(value)

    if not isinstance(value, str):
        return str(value)

    text = value.strip()
    if not text:
        return ""

    parsed = _loads_json(text)
    if parsed is not None:
        return _record_content(parsed, depth=depth + 1)

    embedded = _json_content_line(text)
    if embedded is not None:
        return _record_content(embedded, depth=depth + 1)

    return value


def make_run(*, args: dict[str, Any]) -> Callable[[str], dict[str, Any]]:
    script = _script_component(args.get("script"))
    transform = load_transform(script)

    def run(content: str) -> dict[str, Any]:
        try:
            input_content = _record_content(content)
            output = transform(input_content)
        except Exception as exc:
            raise FatalScriptError(f"{script}: {exc}") from exc

        return {
            "content": output,
            "raw_json": {
                "engine": ENGINE,
                "script": script,
                "args": args,
            },
        }

    return run


def should_retry(exc: BaseException) -> bool:
    return False


__all__ = ["ENGINE", "ENGINE_COMPONENT", "FatalScriptError", "make_run", "should_retry"]
