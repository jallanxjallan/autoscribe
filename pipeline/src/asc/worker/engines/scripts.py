from typing import Any, Callable, Mapping

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

    if key.startswith("asc.scripts."):
        return key.removeprefix("asc.")

    return f"scripts.{key}"


def make_run(*, args: dict[str, Any]) -> Callable[[str], dict[str, Any]]:
    script = _script_component(args.get("script"))
    transform = load_transform(script)

    def run(content: str) -> dict[str, Any]:
        try:
            output = transform(content)
        except Exception as exc:
            raise FatalScriptError(f"{script}: {exc}") from exc

        return {
            "content": output,
            "raw_json": {
                "engine": ENGINE,
                "script": script,
                "args": args,
            },
        }

    return run


def should_retry(exc: BaseException) -> bool:
    return False


__all__ = ["ENGINE", "ENGINE_COMPONENT", "FatalScriptError", "make_run", "should_retry"]
