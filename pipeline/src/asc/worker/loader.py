"""Worker runtime extension loader.

Worker execution calls registered engines through the extensions registry. The
registry owns import-path validation and cacheing; the worker keeps only this
small local alias so the execution boundary does not know registry internals.
"""

from __future__ import annotations

from typing import Any, Callable

from asc.registries.extensions import load_engine_call as _load_engine_call


def load_engine_call(component: str) -> Callable[..., Any]:
    clean_component = component.strip()
    if not clean_component:
        raise ValueError("worker engine component cannot be empty")
    return _load_engine_call(clean_component)


__all__ = ["load_engine_call"]
