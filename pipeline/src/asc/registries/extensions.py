"""Load AutoScribe extension callables from explicit filesystem paths."""

from __future__ import annotations

import importlib.util
import sys
from hashlib import sha256
from pathlib import Path
from threading import RLock
from types import ModuleType
from typing import Any, Callable

from asc.core.config import AUTOSCRIBE_EXTENSIONS_ROOT


_LOAD_LOCK = RLock()
_MODULES: dict[Path, ModuleType] = {}
_CALLABLES: dict[tuple[Path, str], Callable[..., Any]] = {}


def load_extension(component: str, default_callable: str) -> Callable[..., Any]:
    """Load one validated extension callable from an absolute file path.

    ``component`` may identify a file relative to the extensions root, such as
    ``engines.chatgpt``, or a unique bare filename, such as ``chatgpt``. A
    ``:callable`` suffix overrides ``default_callable``.

    Extensions are loaded once per process. Updating extension source requires
    restarting the worker; the loader never mutates ``sys.path`` or reloads a
    live module.
    """
    module_ref, separator, callable_name = component.strip().partition(":")
    if not module_ref:
        raise ValueError("extension component cannot be empty")

    callable_name = callable_name.strip() if separator else default_callable.strip()
    if not callable_name:
        raise ValueError(f"extension callable cannot be empty: {component!r}")

    path = _resolve_path(module_ref)
    cache_key = (path, callable_name)

    with _LOAD_LOCK:
        cached = _CALLABLES.get(cache_key)
        if cached is not None:
            return cached

        module = _MODULES.get(path)
        if module is None:
            module = _load_module(path)
            _MODULES[path] = module

        try:
            entrypoint = getattr(module, callable_name)
        except AttributeError as exc:
            relative = path.relative_to(AUTOSCRIBE_EXTENSIONS_ROOT)
            raise AttributeError(
                f"extension {relative} does not define {callable_name!r}"
            ) from exc

        if not callable(entrypoint):
            relative = path.relative_to(AUTOSCRIBE_EXTENSIONS_ROOT)
            raise TypeError(
                f"extension entry point is not callable: {relative}:{callable_name}"
            )

        _CALLABLES[cache_key] = entrypoint
        return entrypoint


def load_engine_call(component: str) -> Callable[..., Any]:
    return load_extension(component, "make_call")


def load_transform(component: str) -> Callable[..., Any]:
    return load_extension(component, "transform")


def _resolve_path(component: str) -> Path:
    root = AUTOSCRIBE_EXTENSIONS_ROOT
    if not root.is_dir():
        raise FileNotFoundError(f"extensions folder not found: {root}")

    clean = component.strip()
    if not clean:
        raise ValueError("extension component cannot be empty")

    if "." in clean:
        parts = clean.split(".")
        if any(not part or part in {".", ".."} for part in parts):
            raise ValueError(f"invalid extension component: {component!r}")
        relative = Path(*parts)
        path = _component_path(root, relative)
        if path is None:
            raise FileNotFoundError(f"extension not found: {component}")
        return path

    matches = sorted(root.rglob(f"{clean}.py"))
    matches.extend(sorted(root.rglob(f"{clean}/__init__.py")))
    matches = [_validated_path(root, path) for path in matches]

    if not matches:
        raise FileNotFoundError(f"extension not found: {component}")
    if len(matches) > 1:
        paths = ", ".join(str(path.relative_to(root)) for path in matches)
        raise ValueError(f"extension name is ambiguous: {component} ({paths})")

    return matches[0]


def _component_path(root: Path, relative: Path) -> Path | None:
    direct_file = _validated_path(root, root / relative.with_suffix(".py"))
    if direct_file.is_file():
        return direct_file

    direct_package = _validated_path(root, root / relative / "__init__.py")
    if direct_package.is_file():
        return direct_package

    return None


def _validated_path(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"extension path escapes configured root: {path}") from exc
    return resolved


def _load_module(path: Path) -> ModuleType:
    relative = path.relative_to(AUTOSCRIBE_EXTENSIONS_ROOT)
    digest = sha256(str(path).encode("utf-8")).hexdigest()[:12]
    stem_parts = relative.parent.parts if path.name == "__init__.py" else relative.with_suffix("").parts
    safe_parts = [part.replace("-", "_") for part in stem_parts]
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


__all__ = ["load_engine_call", "load_extension", "load_transform"]
