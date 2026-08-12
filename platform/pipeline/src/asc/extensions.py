"""Load executable AutoScribe extensions directly from the extensions folder."""

from __future__ import annotations

import importlib.util
import sys
from hashlib import sha256
from pathlib import Path
from threading import RLock
from types import ModuleType
from typing import Any, Callable

from asc.core.config import AUTOSCRIBE_EXTENSIONS_ROOT
from asc.models.process.result import Transform


_LOAD_LOCK = RLock()
_MODULES: dict[Path, ModuleType] = {}
_CALLABLES: dict[tuple[Path, str], Callable[..., Any]] = {}


def load_runtime_call(runtime: Any) -> Callable[[Any], Any]:
    """Return the executable callable for one runtime record.

    Script steps resolve their ``script`` directly below ``extensions/scripts``
    and are adapted from ``transform(content) -> str`` to the worker artifact
    contract. LLM and RAG steps resolve their ``engine`` directly below
    ``extensions/engines`` and must expose ``make_call``.
    """
    engine_kind = str(runtime.engine_kind).strip()

    if engine_kind == "script":
        script = _clean_component(runtime.script, field="script")
        transform = load_callable("scripts", script, "transform")

        def call(engine_input: Any) -> Transform:
            output = transform(engine_input.content)
            if not isinstance(output, str):
                raise TypeError(
                    f"script {script!r} returned {type(output).__name__}; expected str"
                )
            return Transform.model_validate(
                {
                    "identity": runtime.identity,
                    "ordinal": runtime.ordinal,
                    "content": output,
                    "raw_json": {
                        "engine_kind": "script",
                        "script": script,
                    },
                }
            )

        return call

    if engine_kind in {"llm", "rag"}:
        engine = _clean_component(runtime.engine, field="engine")
        engine = _strip_category(engine, "engines")
        return load_callable("engines", engine, "make_call")

    raise ValueError(f"unsupported runtime engine_kind: {engine_kind!r}")


def load_callable(category: str, component: str, callable_name: str) -> Callable[..., Any]:
    """Load one callable from ``extensions/<category>/<component>.py``."""
    safe_category = _clean_segment(category, field="extension category")
    safe_component = _clean_component(component, field="extension component")
    safe_callable = _clean_segment(callable_name, field="extension callable")

    path = _resolve_path(safe_category, safe_component)
    cache_key = (path, safe_callable)

    with _LOAD_LOCK:
        cached = _CALLABLES.get(cache_key)
        if cached is not None:
            return cached

        module = _MODULES.get(path)
        if module is None:
            module = _load_module(path)
            _MODULES[path] = module

        try:
            entrypoint = getattr(module, safe_callable)
        except AttributeError as exc:
            relative = path.relative_to(AUTOSCRIBE_EXTENSIONS_ROOT)
            raise AttributeError(
                f"extension {relative} does not define {safe_callable!r}"
            ) from exc

        if not callable(entrypoint):
            relative = path.relative_to(AUTOSCRIBE_EXTENSIONS_ROOT)
            raise TypeError(
                f"extension entry point is not callable: {relative}:{safe_callable}"
            )

        _CALLABLES[cache_key] = entrypoint
        return entrypoint


def _resolve_path(category: str, component: str) -> Path:
    root = AUTOSCRIBE_EXTENSIONS_ROOT
    if not root.is_dir():
        raise FileNotFoundError(f"extensions folder not found: {root}")

    relative = Path(category, *component.split("."))
    file_path = _validated_path(root, root / relative.with_suffix(".py"))
    if file_path.is_file():
        return file_path

    package_path = _validated_path(root, root / relative / "__init__.py")
    if package_path.is_file():
        return package_path

    expected = relative.as_posix()
    raise FileNotFoundError(f"extension not found: {expected}")


def _strip_category(component: str, category: str) -> str:
    prefix = f"{category}."
    return component[len(prefix) :] if component.startswith(prefix) else component


def _clean_component(value: Any, *, field: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{field} cannot be empty")
    parts = text.split(".")
    if any(not part or part in {".", ".."} for part in parts):
        raise ValueError(f"invalid {field}: {text!r}")
    for part in parts:
        _clean_segment(part, field=field)
    return text


def _clean_segment(value: str, *, field: str) -> str:
    text = value.strip()
    if not text or not text.replace("-", "_").isidentifier():
        raise ValueError(f"invalid {field}: {value!r}")
    return text


def _validated_path(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"extension path escapes configured root: {path}") from exc
    return resolved


def _load_module(path: Path) -> ModuleType:
    relative = path.relative_to(AUTOSCRIBE_EXTENSIONS_ROOT)
    digest = sha256(str(path).encode("utf-8")).hexdigest()[:12]
    stem = relative.parent.parts if path.name == "__init__.py" else relative.with_suffix("").parts
    safe_parts = [part.replace("-", "_") for part in stem]
    module_name = ".".join(("_autoscribe_extensions", digest, *safe_parts))

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not create import spec for extension: {path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


__all__ = ["load_callable", "load_runtime_call"]
