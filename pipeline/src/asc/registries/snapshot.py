import importlib
import pkgutil
from pathlib import Path
from typing import Any, Iterable

from asc.core.config import (
    AUTOSCRIBE_ENGINE_PACKAGES,
    AUTOSCRIBE_EXTENSIONS_ROOT,
    AUTOSCRIBE_SCRIPT_PACKAGES,
)
from asc.registries.catalog import DEFAULT_REGISTRIES, load_catalog
from asc.registries.extensions import ensure_extensions_on_path

ENGINE_STEP_FIELDS: dict[str, list[str]] = {
    "llm": ["args", "instructions", "ad_hoc"],
    "rag": ["rag_profile", "args", "instructions", "ad_hoc"],
    "script": ["script", "args", "instructions", "ad_hoc"],
}


def build_registry_snapshot() -> dict[str, Any]:
    """Emit the worker-facing runtime component snapshot.

    The registry catalog is still the explicit source of truth when present, but
    development extension packages should also be discoverable without having to
    maintain a separate JSON catalog by hand. This keeps ``asc registry snapshot``
    useful immediately after dropping modules into the configured extensions root.
    """
    catalog = load_catalog()
    catalog_registries = catalog.setdefault("registries", {})

    registries: dict[str, dict[str, Any]] = {
        name: {} for name in DEFAULT_REGISTRIES
    }

    discovered = _discover_extension_registries()
    for registry_name, records in discovered.items():
        registries.setdefault(registry_name, {}).update(records)

    # Explicit catalog entries win over discovered defaults.
    for registry_name in DEFAULT_REGISTRIES:
        records = catalog_registries.setdefault(registry_name, {})
        if not isinstance(records, dict):
            raise TypeError(f"registry catalog section must be an object: {registry_name}")
        registries.setdefault(registry_name, {}).update(
            {str(key): dict(value) for key, value in records.items()}
        )

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


def _discover_extension_registries() -> dict[str, dict[str, dict[str, Any]]]:
    discovered: dict[str, dict[str, dict[str, Any]]] = {
        name: {} for name in DEFAULT_REGISTRIES
    }

    root = AUTOSCRIBE_EXTENSIONS_ROOT
    if not root.is_dir():
        return discovered

    ensure_extensions_on_path()

    for module_name in _iter_package_modules(root, AUTOSCRIBE_ENGINE_PACKAGES):
        record = _engine_record_for(module_name)
        if record is not None:
            discovered["engines"][record["key"]] = record

    for module_name in _iter_package_modules(root, AUTOSCRIBE_SCRIPT_PACKAGES):
        record = _local_script_record_for(module_name)
        if record is not None:
            discovered["local_scripts"][record["key"]] = record

    return discovered


def _iter_package_modules(root: Path, packages: Iterable[str]) -> Iterable[str]:
    for package in packages:
        package_name = package.strip()
        if not package_name:
            continue

        package_path = root.joinpath(*package_name.split("."))
        if not package_path.is_dir():
            continue

        # Include modules below the package. Package __init__ files are ignored
        # unless they have submodules; runtime components should live in named
        # modules such as engines.scripts or scripts.insert_header.
        for module_info in pkgutil.walk_packages(
            [str(package_path)],
            prefix=f"{package_name}.",
        ):
            if module_info.ispkg:
                continue
            yield module_info.name


def _engine_record_for(module_name: str) -> dict[str, Any] | None:
    module = _safe_import(module_name)
    if module is None or not callable(getattr(module, "make_call", None)):
        return None

    kind = _module_attr(module, "REGISTRY_KIND", "ENGINE_KIND", "kind")
    if not kind:
        kind = _default_engine_kind(module_name)

    label = _module_attr(module, "REGISTRY_LABEL", "ENGINE_LABEL", "label")
    if not label:
        label = _title_from_module_name(module_name)

    step_fields = getattr(module, "STEP_FIELDS", None)
    if not isinstance(step_fields, list):
        step_fields = ENGINE_STEP_FIELDS.get(str(kind), ["args", "instructions", "ad_hoc"])

    return {
        "key": module_name,
        "kind": str(kind),
        "label": str(label),
        "module": module_name,
        "step_fields": list(step_fields),
    }


def _local_script_record_for(module_name: str) -> dict[str, Any] | None:
    module = _safe_import(module_name)
    transform_name = _module_attr(module, "TRANSFORM_CALLABLE", "CALLABLE") if module else None
    callable_name = str(transform_name or "transform")

    if module is None or not callable(getattr(module, callable_name, None)):
        return None

    label = _module_attr(module, "REGISTRY_LABEL", "SCRIPT_LABEL", "label")
    if not label:
        label = _title_from_module_name(module_name)

    return {
        "key": module_name,
        "label": str(label),
        "module": module_name,
        "callable": callable_name,
    }


def _safe_import(module_name: str) -> object | None:
    try:
        module = importlib.import_module(module_name)
    except Exception:  # noqa: BLE001 - discovery should skip broken modules.
        return None

    module_file = getattr(module, "__file__", None)
    if not module_file:
        return None

    root = AUTOSCRIBE_EXTENSIONS_ROOT.resolve()
    origin = Path(module_file).resolve()
    if origin != root and root not in origin.parents:
        return None

    return module


def _module_attr(module: object | None, *names: str) -> Any | None:
    if module is None:
        return None
    for name in names:
        value = getattr(module, name, None)
        if value:
            return value
    return None


def _default_engine_kind(module_name: str) -> str:
    leaf = module_name.rsplit(".", 1)[-1]
    if leaf.endswith("s"):
        leaf = leaf[:-1]
    if leaf in ENGINE_STEP_FIELDS:
        return leaf
    return leaf or "llm"


def _title_from_module_name(module_name: str) -> str:
    leaf = module_name.rsplit(".", 1)[-1]
    return leaf.replace("_", " ").replace("-", " ").title()


__all__ = ["ENGINE_STEP_FIELDS", "build_registry_snapshot"]
