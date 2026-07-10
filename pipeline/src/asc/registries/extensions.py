"""Load callables directly from the AutoScribe extensions folder."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable

from asc.core.config import AUTOSCRIBE_EXTENSIONS_ROOT


def load_extension(component: str, default_callable: str) -> Callable[..., Any]:
    """Load an extension callable, reloading its module on every request.

    ``component`` may be a module relative to the extensions root, such as
    ``engines.chatgpt``, or a unique bare module name, such as ``chatgpt``.
    A ``:callable`` suffix overrides ``default_callable``.
    """
    module_ref, separator, callable_name = component.strip().partition(":")
    if not module_ref:
        raise ValueError("extension component cannot be empty")

    module_name = _resolve_module(module_ref)
    callable_name = callable_name if separator else default_callable

    _put_extensions_on_path()
    importlib.invalidate_caches()

    module = sys.modules.get(module_name)
    module = importlib.reload(module) if module else importlib.import_module(module_name)
    return getattr(module, callable_name)


def load_engine_call(component: str) -> Callable[..., Any]:
    return load_extension(component, "make_call")


def load_transform(component: str) -> Callable[..., Any]:
    return load_extension(component, "transform")


def _resolve_module(component: str) -> str:
    root = AUTOSCRIBE_EXTENSIONS_ROOT
    relative = Path(*component.split("."))

    direct_file = root / relative.with_suffix(".py")
    direct_package = root / relative / "__init__.py"
    if direct_file.is_file() or direct_package.is_file():
        return component

    # Bare names are convenient in plans. They are accepted only when unique.
    if "." in component:
        raise FileNotFoundError(f"extension not found: {component}")

    matches = list(root.rglob(f"{component}.py"))
    matches.extend(root.rglob(f"{component}/__init__.py"))

    if not matches:
        raise FileNotFoundError(f"extension not found: {component}")
    if len(matches) > 1:
        paths = ", ".join(str(path.relative_to(root)) for path in matches)
        raise ValueError(f"extension name is ambiguous: {component} ({paths})")

    path = matches[0].relative_to(root)
    parts = path.parent.parts if path.name == "__init__.py" else path.with_suffix("").parts
    return ".".join(parts)


def _put_extensions_on_path() -> None:
    root = AUTOSCRIBE_EXTENSIONS_ROOT
    if not root.is_dir():
        raise FileNotFoundError(f"extensions folder not found: {root}")

    root_string = str(root)
    if root_string not in sys.path:
        sys.path.insert(0, root_string)


__all__ = ["load_engine_call", "load_extension", "load_transform"]
