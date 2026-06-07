from __future__ import annotations

from typing import Any

from asc.core.config import (
    AUTOSCRIBE_ENGINE_PACKAGES,
    AUTOSCRIBE_EXTENSIONS_ROOT,
    AUTOSCRIBE_SCRIPT_PACKAGES,
)
from asc.registries.catalog import DEFAULT_REGISTRIES, load_catalog

ENGINE_STEP_FIELDS: dict[str, list[str]] = {
    "llm": ["args", "instructions", "ad_hoc"],
    "rag": ["rag_profile", "args", "instructions", "ad_hoc"],
    "script": ["script", "args", "instructions", "ad_hoc"],
}


def build_registry_snapshot() -> dict[str, Any]:
    """Emit the worker-facing runtime component snapshot."""
    catalog = load_catalog()
    catalog_registries = catalog.setdefault("registries", {})

    registries: dict[str, dict[str, Any]] = {}
    for registry_name in DEFAULT_REGISTRIES:
        records = catalog_registries.setdefault(registry_name, {})
        if not isinstance(records, dict):
            raise TypeError(f"registry catalog section must be an object: {registry_name}")
        registries[registry_name] = {
            str(key): dict(value) for key, value in records.items()
        }

    return {
        "schema_version": 1,
        "type": "autoscribe.registries",
        "sources": {
            "extension_root": str(AUTOSCRIBE_EXTENSIONS_ROOT),
            "engine_packages": list(AUTOSCRIBE_ENGINE_PACKAGES),
            "local_script_packages": list(AUTOSCRIBE_SCRIPT_PACKAGES),
        },
        "registries": registries,
    }


__all__ = ["ENGINE_STEP_FIELDS", "build_registry_snapshot"]
