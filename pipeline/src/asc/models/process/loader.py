"""Process model loading from Redis keys."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from asc.redis.key import RedisKey


def key_kind(key: str | RedisKey) -> str:
    """Return the model kind from a full Redis key."""

    return (key if isinstance(key, RedisKey) else RedisKey(str(key).strip())).kind


def pascal_case(value: str) -> str:
    """Convert a Redis kind to its model class name."""

    text = str(value or "").replace("-", "_").strip("_")
    if not text:
        raise ValueError("kind must be non-empty")
    return "".join(part[:1].upper() + part[1:] for part in text.split("_") if part)


def model_class_for_key(key: str) -> type[Any]:
    """Resolve the process model class implied by the key kind."""

    kind = key_kind(key)
    module_name = kind.replace("-", "_")
    class_name = pascal_case(kind)

    module = import_module(f"asc.models.process.{module_name}")
    model_class = getattr(module, class_name)
    if not isinstance(model_class, type):
        raise TypeError(f"asc.models.process.{module_name}.{class_name} is not a class")
    return model_class


def load_key(key: str) -> Any:
    """Load the Redis model instance identified by ``key``."""

    model_class = model_class_for_key(key)
    return model_class.load(key)


__all__ = ["key_kind", "load_key", "model_class_for_key", "pascal_case"]
