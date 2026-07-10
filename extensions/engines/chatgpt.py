from __future__ import annotations

from typing import Any

from openai import OpenAI

from asc.core.config import config
from asc.models.process.result import ExternalFailure, Response


ENGINE = "chatgpt"

MODEL_LABELS: dict[str, str] = {
    # Best / flagship
    "best": "gpt-5.5",
    "frontier": "gpt-5.5",

    # Highest-quality / expensive
    "pro": "gpt-5.5-pro",

    # Strong general production model
    "standard": "gpt-5.4",

    # Cheaper / faster production model
    "cheap": "gpt-5.4-mini",
    "mini": "gpt-5.4-mini",

    # Cheapest / fastest high-volume model
    "nano": "gpt-5.4-nano",
}

ENGINE_COMPONENT = {
    "label": "ChatGPT",
    "kind": "llm",
    "step_fields": [
        "model",
        "instructions",
        "temperature",
        "max_output_tokens",
    ],
    "models": MODEL_LABELS,
}


def make_call(*, content: Any, step: Any, call: Any) -> Response | ExternalFailure:
    """Run one ChatGPT Responses API call.

    The worker/registry has already validated the content and step models.
    This engine owns only the provider-specific request shape and maps the
    provider object into the runtime result models.
    """

    # model = MODEL_LABELS[step.model]
    model = "gpt-5.4-nano"
    request: dict[str, Any] = {
        "model": model,
        "input": content.content,
    }

    instructions = _instructions_text(step.instructions)
    if instructions:
        request["instructions"] = instructions

    temperature = getattr(step, "temperature", None)
    if temperature is not None:
        request["temperature"] = temperature

    max_output_tokens = getattr(step, "max_output_tokens", None)
    if max_output_tokens is not None:
        request["max_output_tokens"] = max_output_tokens

    try:
        result = OpenAI(api_key=config.open_ai_key).responses.create(**request)
    except Exception as exc:
        return ExternalFailure(
            identity=call.identity,
            ordinal=step.ordinal,
            content=str(exc),
            failure_reason=type(exc).__name__,
            raw_json={
                "engine": ENGINE,
                "model_label": step.model,
                "model": model,
                "error": str(exc),
                "error_type": type(exc).__name__,
            },
            boundary=ENGINE,
        )

    raw_json = result.model_dump(mode="json")
    return Response(
        identity=call.identity,
        ordinal=step.ordinal,
        content=result.output_text,
        raw_json={
            "engine": ENGINE,
            "model_label": step.model,
            "model": model,
            "provider": raw_json,
        },
    )


def _instructions_text(instructions: list[str]) -> str:
    return "\n\n".join(instructions).strip()


__all__ = ["ENGINE", "ENGINE_COMPONENT", "MODEL_LABELS", "make_call"]
