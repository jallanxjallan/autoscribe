"""Build the Obsidian plan-compiler snapshot from the live extensions tree."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Iterable

from asc.core.config import (
    AUTOSCRIBE_ENGINE_PACKAGES,
    AUTOSCRIBE_EXTENSIONS_ROOT,
    AUTOSCRIBE_SCRIPT_PACKAGES,
)

ENGINE_STEP_FIELDS: dict[str, list[str]] = {
    "llm": ["args", "instructions", "ad_hoc"],
    "rag": ["rag_profile", "args", "instructions", "ad_hoc"],
    "script": ["script", "args", "instructions", "ad_hoc"],
}


def build_registry_snapshot() -> dict[str, Any]:
    """Describe every extension available to the Obsidian plan compiler.

    This is discovery, not validation. Python files are listed whether or not
    they currently import or expose the expected runtime callable.
    """
    return {
        "schema_version": 1,
        "type": "autoscribe.registries",
        "sources": {
            "extension_root": str(AUTOSCRIBE_EXTENSIONS_ROOT),
            "engine_packages": list(AUTOSCRIBE_ENGINE_PACKAGES),
            "local_script_packages": list(AUTOSCRIBE_SCRIPT_PACKAGES),
        },
        "registries": {
            "engines": _engine_records(AUTOSCRIBE_ENGINE_PACKAGES),
            "local_scripts": _script_records(AUTOSCRIBE_SCRIPT_PACKAGES),
            "rag_profiles": _rag_profile_records(),
        },
    }


def _engine_records(packages: Iterable[str]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for key, module, path in _python_extensions(packages):
        metadata = _literal_module_metadata(path)
        kind = str(
            metadata.get("REGISTRY_KIND")
            or metadata.get("ENGINE_KIND")
            or _default_engine_kind(key)
        )
        label = str(
            metadata.get("REGISTRY_LABEL")
            or metadata.get("ENGINE_LABEL")
            or _title(key)
        )
        step_fields = metadata.get("STEP_FIELDS")
        if not isinstance(step_fields, list):
            step_fields = ENGINE_STEP_FIELDS.get(kind, ENGINE_STEP_FIELDS["llm"])

        records[key] = {
            "key": key,
            "kind": kind,
            "label": label,
            "module": module,
            "step_fields": list(step_fields),
        }
    return records


def _script_records(packages: Iterable[str]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for key, module, path in _python_extensions(packages):
        metadata = _literal_module_metadata(path)
        label = str(
            metadata.get("REGISTRY_LABEL")
            or metadata.get("SCRIPT_LABEL")
            or _title(key)
        )
        callable_name = str(
            metadata.get("TRANSFORM_CALLABLE")
            or metadata.get("CALLABLE")
            or "transform"
        )
        records[key] = {
            "key": key,
            "label": label,
            "module": module,
            "callable": callable_name,
        }
    return records


def _rag_profile_records() -> dict[str, dict[str, Any]]:
    root = AUTOSCRIBE_EXTENSIONS_ROOT / "rag_profiles"
    if not root.is_dir():
        return {}

    records: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("_"):
            continue
        key = ".".join(path.relative_to(root).with_suffix("").parts)
        records[key] = {
            "key": key,
            "label": _title(key),
            "path": str(path.relative_to(AUTOSCRIBE_EXTENSIONS_ROOT)),
        }
    return records


def _python_extensions(
    packages: Iterable[str],
) -> Iterable[tuple[str, str, Path]]:
    root = AUTOSCRIBE_EXTENSIONS_ROOT
    for package in packages:
        package = package.strip()
        if not package:
            continue
        package_root = root.joinpath(*package.split("."))
        if not package_root.is_dir():
            continue

        for path in sorted(package_root.rglob("*.py")):
            if path.name == "__init__.py" or path.name.startswith("_"):
                continue
            relative = path.relative_to(package_root).with_suffix("")
            key = ".".join(relative.parts)
            module = ".".join((*package.split("."), *relative.parts))
            yield key, module, path


def _literal_module_metadata(path: Path) -> dict[str, Any]:
    """Read simple top-level constants without importing the extension."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError):
        return {}

    metadata: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            metadata[target.id] = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            continue
    return metadata


def _default_engine_kind(key: str) -> str:
    leaf = key.rsplit(".", 1)[-1].lower()
    if "rag" in leaf:
        return "rag"
    if "script" in leaf or "local" in leaf:
        return "script"
    return "llm"


def _title(key: str) -> str:
    leaf = key.rsplit(".", 1)[-1]
    return leaf.replace("_", " ").replace("-", " ").title()


__all__ = ["ENGINE_STEP_FIELDS", "build_registry_snapshot"]
