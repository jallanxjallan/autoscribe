"""Runtime model discovery from Redis keys.

Runtime Redis keys carry the model selector in their final segment::

    runtime:<identity>:cursor
    runtime:<identity>:call
    runtime:<identity>:result.1
    runtime:<identity>:worker-job

The loader derives the model class from that segment instead of keeping a
parallel table of bare strings in every daemon.  The segment before any dot is
normalised to PascalCase, then resolved from the runtime model modules.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any, TypeVar

T = TypeVar("T")


def key_model_segment(key: str) -> str:
    """Return the model selector from a full Redis key.

    ``runtime:01ABC:result.1`` resolves to ``result``.  The dot suffix remains
    part of the record identity, not the model selector.
    """

    text = str(key or "").strip()
    if not text or ":" not in text:
        raise ValueError(f"expected full Redis key, got {key!r}")
    return text.rsplit(":", 1)[-1].split(".", 1)[0]


def pascal_case(value: str) -> str:
    """Convert a Redis key segment to a model class stem."""

    text = str(value or "").replace("-", "_").strip("_")
    if not text:
        raise ValueError("model segment must be non-empty")
    return "".join(part[:1].upper() + part[1:] for part in text.split("_") if part)


def _module_candidates(segment: str) -> list[str]:
    normalized = segment.replace("-", "_")
    parts = [part for part in normalized.split("_") if part]
    candidates = [normalized]
    if parts:
        candidates.append(parts[-1])
        candidates.append(parts[0])
    # Preserve order while removing duplicates.
    return list(dict.fromkeys(candidates))


def model_class_for_key(key: str) -> type[Any]:
    """Resolve the runtime model class implied by ``key``."""

    segment = key_model_segment(key)
    class_name = pascal_case(segment)
    class_candidates = [class_name, f"{class_name}Record"]

    import_errors: list[str] = []
    for module_name in _module_candidates(segment):
        try:
            module = import_module(f"asc.models.runtime.{module_name}")
        except ModuleNotFoundError as exc:
            import_errors.append(str(exc))
            continue
        for candidate in class_candidates:
            model_class = getattr(module, candidate, None)
            if isinstance(model_class, type):
                return model_class

    raise LookupError(
        f"cannot resolve runtime model for key {key!r}; "
        f"segment={segment!r}, class candidates={class_candidates!r}, "
        f"module candidates={_module_candidates(segment)!r}, import errors={import_errors!r}"
    )


def load_key(key: str) -> Any:
    """Load the Redis model instance identified by ``key``."""

    model_class = model_class_for_key(key)
    load = getattr(model_class, "load", None)
    if not callable(load):
        raise TypeError(f"runtime model {model_class.__name__} has no load() method")
    return load(key)


__all__ = ["key_model_segment", "load_key", "model_class_for_key", "pascal_case"]
