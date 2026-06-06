from __future__ import annotations

from typing import Any

from asc.models.control.driver import DriverRecord
from asc.models.control.instruction import InstructionRecord
from asc.registries.extensions import load_transform


ENGINE = "scripts"
ENGINE_COMPONENT = {
    "label": "Local script",
    "kind": "script",
    "step_fields": ["script", "args", "instructions", "ad_hoc"],
}


def make_call(
    *,
    prompt: str,
    driver: DriverRecord,
    instructions: list[InstructionRecord],
) -> dict[str, Any]:
    script = driver.args["script"]
    transform = load_transform(script)
    raw = transform(prompt)
    return handle_response(raw, script=script)


def handle_response(raw: str, *, script: str) -> dict[str, Any]:
    content = raw.strip()
    return {
        "provider": ENGINE,
        "status": "success" if content else "failure",
        "content": content or None,
        "fail_message": None if content else f"{script} returned empty content.",
        "record": {
            "script": script,
            "content": raw,
        },
    }
