from __future__ import annotations

from typing import Any, Mapping


ENGINE = "rag"

ENGINE_COMPONENT = {
    "label": "RAG",
    "kind": "rag",
    "step_fields": [
        "rag_profile",
        "instructions",
    ],
}


def make_call(*, step: Any, content: Any, task: Any) -> dict[str, Any]:
    args = _step_args(step)
    profile = args.get("rag_profile") or getattr(step, "rag_profile", "") or ""

    return {
        "content": _content_text(content),
        "engine": ENGINE,
        "profile": profile,
        "raw_json": {
            "engine": ENGINE,
            "profile": profile,
            "args": dict(args),
        },
    }


def _step_args(step: Any) -> Mapping[str, Any]:
    value = getattr(step, "args", None)
    return value if isinstance(value, Mapping) else {}


def _content_text(content: Any) -> str:
    value = getattr(content, "content", content)
    return "" if value is None else str(value)


__all__ = ["ENGINE", "ENGINE_COMPONENT", "make_call"]
