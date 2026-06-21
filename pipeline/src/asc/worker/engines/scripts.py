from typing import Any, Callable, Mapping

from asc.models.process.result import Failure, Response
from asc.registries.extensions import load_transform

ENGINE = "scripts"
ENGINE_COMPONENT = {
    "label": "Local script",
    "kind": "script",
    "step_fields": ["script", "args", "instructions", "ad_hoc"],
}


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

    # Accept older values that were stored as module-ish paths.
    if key.startswith("asc.scripts."):
        return key.removeprefix("asc.")

    return f"scripts.{key}"


def make_call(*, args: dict[str, Any]) -> Callable[[str], Response | Failure]:
    script = _script_component(args.get("script"))
    transform = load_transform(script)

    def call(content: str) -> Response | Failure:
        try:
            output = transform(content)
        except Exception as exc:
            return Failure(
                content=content,
                failure_reason=type(exc).__name__,
                raw_json={
                    "engine": ENGINE,
                    "script": script,
                    "args": args,
                    "error": str(exc),
                },
            )

        return Response(
            content=output,
            raw_json={
                "engine": ENGINE,
                "script": script,
                "args": args,
            },
        )

    return call


def should_retry(exc: BaseException) -> bool:
    return False


__all__ = ["ENGINE", "ENGINE_COMPONENT", "FatalScriptError", "make_call", "should_retry"]
