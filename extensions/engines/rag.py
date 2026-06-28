from typing import Any


ENGINE = "rag"

ENGINE_COMPONENT = {
    "label": "RAG Stub",
    "kind": "rag",
    "step_fields": [
        "rag_profile",
        "instructions",
    ],
}


def make_call(
    *,
    prompt: str,
    instructions: list[Any] | None = None,
    step_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args = dict(step_args or {})
    return {
        "content": prompt,
        "engine": ENGINE,
        "profile": args.get("rag_profile") or "",
    }


def make_run(*, args: dict[str, Any]):
    def run(content: str) -> str:
        return content

    return run


def should_retry(exc: BaseException) -> bool:
    return False


__all__ = [
    "ENGINE",
    "ENGINE_COMPONENT",
    "make_call",
    "make_run",
    "should_retry",
]
