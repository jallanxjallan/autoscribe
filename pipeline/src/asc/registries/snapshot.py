from __future__ import annotations

from typing import Any

from asc.core.config import AUTOSCRIBE_EXTENSIONS_ROOT
from asc.registries.catalog import DEFAULT_REGISTRIES, load_catalog

ENGINE_STEP_FIELDS: dict[str, list[str]] = {
    "llm": ["args", "instructions", "ad_hoc"],
    "LLM": ["args", "instructions", "ad_hoc"],
    "rag": ["rag_profile", "args", "instructions", "ad_hoc"],
    "script": ["script", "args", "instructions", "ad_hoc"],
    "local": ["script", "args", "instructions", "ad_hoc"],
}


def build_registry_snapshot() -> dict[str, Any]:
    """
    Emit the worker-facing runtime component snapshot.

    The registry catalog is intentionally limited to immutable runtime
    components: engines, local scripts, and RAG profiles. Uploaded controls
    such as drivers, instructions, and plans live in the control slugmap and
    are reported by ``asc control snapshot``.
    """
    catalog = load_catalog()
    catalog_registries = catalog.setdefault("registries", {})

    registries: dict[str, dict[str, Any]] = {}
    for registry_name in DEFAULT_REGISTRIES:
        records = catalog_registries.setdefault(registry_name, {})
        if not isinstance(records, dict):
            raise TypeError(f"registry catalog section must be an object: {registry_name}")
        registries[registry_name] = {str(key): dict(value) for key, value in records.items()}

    

    return {
        "schema_version": 1,
        "type": "autoscribe.registries",
        "sources": {
            "extension_root": str(AUTOSCRIBE_EXTENSIONS_ROOT),
            "engine_packages": ["autoscribe_engines"],
            "local_script_packages": ["autoscribe_scripts"],
        },
        "registries": registries,
    }


__all__ = ["ENGINE_STEP_FIELDS", "build_registry_snapshot"]
