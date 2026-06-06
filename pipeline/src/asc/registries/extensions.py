from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from typing import Callable, Iterable

from asc.core.config import (
    AUTOSCRIBE_ENGINE_PACKAGES,
    AUTOSCRIBE_EXTENSIONS_ROOT,
    AUTOSCRIBE_SCRIPT_PACKAGES,
)

DEFAULT_TRANSFORM = "transform"


def ensure_extensions_on_path() -> None:
    """Make the hard-coded extensions root importable for runtime components."""
    root = AUTOSCRIBE_EXTENSIONS_ROOT

    if not root.is_dir():
        raise FileNotFoundError(f"AutoScribe extensions root not found: {root}")

    root_string = str(root)
    if root_string not in sys.path:
        sys.path.insert(0, root_string)


def load_engine_call(component: str) -> Callable[..., dict]:
    """Load an engine make_call function from an importable component name."""
    module = _import_component(
        component,
        allowed_packages=AUTOSCRIBE_ENGINE_PACKAGES,
        label="engine",
    )
    make_call = getattr(module, "make_call", None)

    if not callable(make_call):
        raise TypeError(f"Engine component {component!r} must define make_call(...)")

    return make_call


def load_transform(component: str) -> Callable[[str], str]:
    """Load a local script transform by importable component name.

    The normal pointer is the module import name:

        autoscribe_scripts.strip_sentinels

    A non-default callable can be named only when needed:

        autoscribe_scripts.some_module:rewrite
    """
    module_name, callable_name = _split_callable_pointer(
        component,
        default_callable=DEFAULT_TRANSFORM,
        label="local script",
    )
    module = _import_component(
        module_name,
        allowed_packages=AUTOSCRIBE_SCRIPT_PACKAGES,
        label="local script",
    )
    transform = getattr(module, callable_name, None)

    if not callable(transform):
        raise TypeError(
            f"Local script component {component!r} must define "
            f"{callable_name}(content: str) -> str"
        )

    return transform


def _import_component(
    component: str,
    *,
    allowed_packages: Iterable[str],
    label: str,
) -> object:
    module_name = _validate_module_name(component, label=label)
    _validate_allowed_package(module_name, allowed_packages=allowed_packages, label=label)
    ensure_extensions_on_path()

    module = import_module(module_name)
    _verify_module_origin(module, component=module_name, label=label)
    return module


def _split_callable_pointer(
    component: str,
    *,
    default_callable: str,
    label: str,
) -> tuple[str, str]:
    pointer = component.strip()

    if not pointer:
        raise ValueError(f"{label.title()} component import name cannot be empty")

    module_name, sep, callable_name = pointer.partition(":")
    callable_name = callable_name if sep else default_callable

    _validate_module_name(module_name, label=label)

    if not callable_name.isidentifier() or callable_name.startswith("_"):
        raise ValueError(f"Invalid {label} callable name: {callable_name!r}")

    return module_name, callable_name


def _validate_module_name(component: str, *, label: str) -> str:
    name = component.strip()

    if not name:
        raise ValueError(f"{label.title()} component import name cannot be empty")

    parts = name.split(".")
    if any(not part.isidentifier() or part.startswith("_") for part in parts):
        raise ValueError(f"Invalid {label} component import name: {component!r}")

    return name


def _validate_allowed_package(
    module_name: str,
    *,
    allowed_packages: Iterable[str],
    label: str,
) -> None:
    package_names = tuple(allowed_packages)

    if not package_names:
        raise ValueError(f"No allowed packages configured for {label} components")

    if not any(
        module_name == package or module_name.startswith(f"{package}.")
        for package in package_names
    ):
        allowed = ", ".join(package_names)
        raise ValueError(
            f"{label.title()} component {module_name!r} is outside allowed packages: "
            f"{allowed}"
        )


def _verify_module_origin(module: object, *, component: str, label: str) -> None:
    module_file = getattr(module, "__file__", None)
    package_paths = getattr(module, "__path__", None)

    if module_file:
        origin = Path(module_file).resolve()
        if origin == AUTOSCRIBE_EXTENSIONS_ROOT or AUTOSCRIBE_EXTENSIONS_ROOT in origin.parents:
            return

    if package_paths:
        for package_path in package_paths:
            origin = Path(package_path).resolve()
            if origin == AUTOSCRIBE_EXTENSIONS_ROOT or AUTOSCRIBE_EXTENSIONS_ROOT in origin.parents:
                return

    raise ImportError(
        f"{label.title()} component {component!r} resolved outside extensions root: "
        f"{AUTOSCRIBE_EXTENSIONS_ROOT}"
    )


__all__ = [
    "DEFAULT_TRANSFORM",
    "ensure_extensions_on_path",
    "load_engine_call",
    "load_transform",
]
