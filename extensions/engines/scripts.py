from __future__ import annotations

from typing import Any

from asc.registries.extensions import load_transform


ENGINE = "scripts"
ENGINE_COMPONENT = {
    "label": "Local script",
    "kind": "script",
    "step_fields": ["script", "args", "instructions", "ad_hoc"],
}


def make_call(*, step: Any, content: Any, task: Any) -> dict[str, Any]:
    transform = load_transform(step.script)
    output = transform(_content_text(content))

    return {
        "content": output,
        "engine": ENGINE,
        "script": step.script,
        "raw_json": {
            "engine": ENGINE,
            "script": step.script,
            "args": step.args,
        },
    }


def _content_text(content: Any) -> str:
    value = getattr(content, "content", content)
    return "" if value is None else str(value)


__all__ = ["ENGINE", "ENGINE_COMPONENT", "make_call"]
