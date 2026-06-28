from typing import Any


ENGINE = "chatgpt"

ENGINE_COMPONENT = {
    "label": "ChatGPT Stub",
    "kind": "llm",
    "step_fields": [
        "model",
        "instructions",
        "temperature",
        "max_tokens",
    ],
}

DEFAULT_MODEL = "chatgpt-stub"


def _instruction_text(instructions: Any) -> str:
    if not instructions:
        return ""

    if isinstance(instructions, str):
        return instructions.strip()

    if isinstance(instructions, list):
        parts: list[str] = []
        for item in instructions:
            if isinstance(item, str):
                parts.append(item.strip())
            elif isinstance(item, dict):
                label = item.get("label") or item.get("slug") or item.get("key") or "instruction"
                content = item.get("content") or item.get("text") or item.get("body") or ""
                if content:
                    parts.append(f"# {label}\n\n{content}".strip())
                else:
                    parts.append(str(item))
            else:
                parts.append(str(item))
        return "\n\n---\n\n".join(part for part in parts if part)

    return str(instructions).strip()


def make_call(
    *,
    prompt: str,
    instructions: list[Any] | None = None,
    step_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args = dict(step_args or {})
    model = args.get("model") or DEFAULT_MODEL
    instruction_block = _instruction_text(instructions or args.get("instructions") or [])

    content = (
        f"Model: {model}\n\n"
        f"Instructions:\n"
        f"{instruction_block or '(none)'}\n\n"
        f"Content:\n"
        f"```text\n"
        f"{prompt}\n"
        f"```"
    )

    return {
        "content": content,
        "model": model,
        "engine": ENGINE,
    }


def make_run(*, args: dict[str, Any]):
    frozen_args = dict(args or {})

    def run(content: str) -> str:
        result = make_call(
            prompt=content,
            instructions=frozen_args.get("instructions") or [],
            step_args=frozen_args,
        )
        return result["content"]

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
