from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from asc.core.config import AUTOSCRIBE_EXTENSIONS_ROOT

CATALOG_FILENAME = "registry.json"
DEFAULT_REGISTRIES = (
    "engines",
    "local_scripts",
    "rag_profiles",
)


def catalog_path() -> Path:
    return AUTOSCRIBE_EXTENSIONS_ROOT / CATALOG_FILENAME


def empty_catalog() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "type": "autoscribe.registry_catalog",
        "registries": {name: {} for name in DEFAULT_REGISTRIES},
    }


def load_catalog() -> dict[str, Any]:
    path = catalog_path()
    if not path.exists():
        return empty_catalog()

    with path.open("r", encoding="utf-8") as handle:
        catalog = json.load(handle)

    if not isinstance(catalog, dict):
        raise TypeError(f"registry catalog must be a JSON object: {path}")

    registries = catalog.setdefault("registries", {})
    if not isinstance(registries, dict):
        raise TypeError(f"registry catalog registries must be an object: {path}")

    for name in DEFAULT_REGISTRIES:
        value = registries.setdefault(name, {})
        if not isinstance(value, dict):
            raise TypeError(f"registry catalog section must be an object: {name}")

    catalog.setdefault("schema_version", 1)
    catalog.setdefault("type", "autoscribe.registry_catalog")
    return catalog


def save_catalog(catalog: dict[str, Any]) -> Path:
    path = catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(catalog, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def list_registered_components(registry: str) -> dict[str, dict[str, Any]]:
    catalog = load_catalog()
    records = catalog.get("registries", {}).get(registry, {})
    if not isinstance(records, dict):
        raise TypeError(f"registry catalog section must be an object: {registry}")
    return {str(key): dict(value) for key, value in records.items()}


def upsert_registered_component(
    *,
    registry: str,
    key: str,
    record: dict[str, Any],
) -> Path:
    clean_registry = _clean_name(registry, label="registry")
    clean_key = key.strip()
    if not clean_key:
        raise ValueError("registry component key cannot be empty")

    catalog = load_catalog()
    registries = catalog.setdefault("registries", {})
    records = registries.setdefault(clean_registry, {})
    if not isinstance(records, dict):
        raise TypeError(f"registry catalog section must be an object: {clean_registry}")

    stored = dict(record)
    stored["key"] = clean_key
    records[clean_key] = stored
    return save_catalog(catalog)


def remove_registered_component(*, registry: str, key: str) -> bool:
    clean_registry = _clean_name(registry, label="registry")
    clean_key = key.strip()
    if not clean_key:
        raise ValueError("registry component key cannot be empty")

    catalog = load_catalog()
    records = catalog.get("registries", {}).get(clean_registry, {})
    if not isinstance(records, dict):
        raise TypeError(f"registry catalog section must be an object: {clean_registry}")

    existed = clean_key in records
    records.pop(clean_key, None)
    save_catalog(catalog)
    return existed


def _clean_name(value: str, *, label: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError(f"{label} name cannot be empty")
    if any(part.startswith("_") or not part.isidentifier() for part in name.split("_")):
        raise ValueError(f"invalid {label} name: {value!r}")
    return name


__all__ = [
    "CATALOG_FILENAME",
    "DEFAULT_REGISTRIES",
    "catalog_path",
    "empty_catalog",
    "list_registered_components",
    "load_catalog",
    "remove_registered_component",
    "save_catalog",
    "upsert_registered_component",
]
