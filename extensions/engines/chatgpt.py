from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from openai import OpenAI


ENGINE = "chatgpt"

ENGINE_COMPONENT = {
    "label": "ChatGPT",
    "kind": "llm",
    "step_fields": [
        "model",
        "instructions",
        "temperature",
        "max_output_tokens",
    ],
}


def make_call(*, step: Any, content: Any, task: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": step.model,
        "input": _content_text(content),
    }

    instructions = _instruction_text(step.instructions)
    if instructions:
        request["instructions"] = instructions

    for name in ("temperature", "max_output_tokens"):
        value = getattr(step, name, None)
        if value is not None:
            request[name] = value

    response = OpenAI().responses.create(**request)

    return {
        "content": response.output_text,
        "engine": ENGINE,
        "model": step.model,
        "raw_json": response.model_dump(mode="json"),
    }


def _content_text(content: Any) -> str:
    value = getattr(content, "content", content)
    return "" if value is None else str(value)


def _instruction_text(value: Any) -> str:
    if value in (None, ""):
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, Mapping):
        return _mapping_instruction_text(value)

    if isinstance(value, Iterable):
        parts = [_instruction_text(item) for item in value]
        return "\n\n---\n\n".join(part for part in parts if part)

    return str(value).strip()


def _mapping_instruction_text(value: Mapping[Any, Any]) -> str:
    label = value.get("label") or value.get("slug") or value.get("key")
    for field in ("content", "text", "body", "prompt"):
        text = value.get(field)
        if text:
            body = str(text).strip()
            return f"# {label}\n\n{body}" if label else body
    return "\n".join(f"{key}: {item}" for key, item in value.items()).strip()


__all__ = ["ENGINE", "ENGINE_COMPONENT", "make_call"]
