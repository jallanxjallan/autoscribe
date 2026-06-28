from collections.abc import Callable, Iterable, Mapping
from typing import Any

ENGINE = "llm"
ENGINE_COMPONENT = {
    "label": "ChatGPT",
    "kind": "llm",
    "step_fields": ["model", "instructions", "temperature", "max_tokens"],
}

DEFAULT_MODEL = "chatgpt-stub"


def make_run(*, args: dict[str, Any]) -> Callable[[str], str]:
    """Return a deterministic local ChatGPT stub.

    This does not call OpenAI. It formats the worker input as the content that
    a real ChatGPT call would receive, with step instructions first and the
    source content fenced as a code block. The worker executor is still
    responsible for wrapping the returned string in a Response record.
    """

    instructions = _instruction_text(args.get("instructions"))
    model = str(args.get("model") or DEFAULT_MODEL)

    def run(content: str) -> str:
        source = str(content)
        parts = [f"Model: {model}"]

        if instructions:
            parts.extend(["", "Instructions:", instructions])

        parts.extend(["", "Content:", "```", source, "```"])
        return "\n".join(parts)

    return run


def make_call(
    *,
    prompt: str,
    instructions: list[Any] | None = None,
    step_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Registry/runtime adapter for the same local ChatGPT stub.

    This keeps extension-style engine calls and worker-style engine runs aligned
    during development. A real ChatGPT implementation can replace this function
    later without changing registry callers.
    """

    args = dict(step_args or {})
    args["instructions"] = list(instructions or args.get("instructions") or [])
    content = make_run(args=args)(prompt)
    return {
        "engine": ENGINE,
        "model": str(args.get("model") or DEFAULT_MODEL),
        "content": content,
    }


def should_retry(exc: BaseException) -> bool:
    return False


def _instruction_text(value: object) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, Mapping):
        return _mapping_instruction_text(value)

    if isinstance(value, Iterable):
        lines = [_one_instruction_text(item) for item in value]
        return "\n\n".join(line for line in lines if line)

    return str(value).strip()


def _one_instruction_text(value: object) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, Mapping):
        return _mapping_instruction_text(value)

    return str(value).strip()


def _mapping_instruction_text(value: Mapping[object, object]) -> str:
    for key in ("content", "text", "body", "prompt"):
        text = value.get(key)
        if text:
            return str(text).strip()

    return "\n".join(f"{key}: {item}" for key, item in value.items()).strip()


__all__ = [
    "DEFAULT_MODEL",
    "ENGINE",
    "ENGINE_COMPONENT",
    "make_call",
    "make_run",
    "should_retry",
]
