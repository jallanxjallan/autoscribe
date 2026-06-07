from __future__ import annotations

from typing import Any

from asc.registries.extensions import load_transform


ENGINE = "scripts"
ENGINE_COMPONENT = {
    "label": "Local script",
    "kind": "script",
    "step_fields": ["script", "args", "instructions", "ad_hoc"],
}


def make_call(*, args: dict[str, Any]) -> Any:
    script = args["script"]
    transform = load_transform(script)

    def call(content: str) -> str:
        return transform(content)

    return call