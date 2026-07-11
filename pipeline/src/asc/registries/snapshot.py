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
    "llm": ["model", "instruction_keys", "temperature", "max_output_tokens"],
    "rag": ["rag_profile", "instruction_keys"],
    "script": ["script", "instruction_keys"],
}


def build_registry_snapshot() -> dict[str, Any]:
    """Describe extensions available to the Obsidian plan compiler.

    Extension modules are parsed rather than imported, so generating a snapshot
    does not execute provider code or require provider dependencies.
    """
    engines, models = _engine_and_model_records(AUTOSCRIBE_ENGINE_PACKAGES)
    return {
        "schema_version": 2,
        "type": "autoscribe.registries",
        "sources": {
            "extension_root": str(AUTOSCRIBE_EXTENSIONS_ROOT),
            "engine_packages": list(AUTOSCRIBE_ENGINE_PACKAGES),
            "local_script_packages": list(AUTOSCRIBE_SCRIPT_PACKAGES),
        },
        "registries": {
            "engines": engines,
            "models": models,
            "local_scripts": _script_records(AUTOSCRIBE_SCRIPT_PACKAGES),
            "rag_profiles": _rag_profile_records(),
        },
    }


def _engine_and_model_records(
    packages: Iterable[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    engines: dict[str, dict[str, Any]] = {}
    models: dict[str, dict[str, Any]] = {}

    for key, module, path in _python_extensions(packages):
        metadata = _literal_module_metadata(path)
        component = metadata.get("ENGINE_COMPONENT")
        component = component if isinstance(component, dict) else {}

        kind = str(
            component.get("kind")
            or metadata.get("REGISTRY_KIND")
            or metadata.get("ENGINE_KIND")
            or _default_engine_kind(key)
        )
        label = str(
            component.get("label")
            or metadata.get("REGISTRY_LABEL")
            or metadata.get("ENGINE_LABEL")
            or _title(key)
        )
        step_fields = component.get("step_fields") or metadata.get("STEP_FIELDS")
        if not isinstance(step_fields, list):
            step_fields = ENGINE_STEP_FIELDS.get(kind, ENGINE_STEP_FIELDS["llm"])

        engine_record: dict[str, Any] = {
            "key": key,
            "kind": kind,
            "label": label,
            "module": module,
            "step_fields": list(step_fields),
        }

        component_models = component.get("models")
        if not isinstance(component_models, dict):
            component_models = metadata.get("MODEL_LABELS")
        model_keys = _add_model_records(models, key, component_models)
        if model_keys:
            engine_record["models"] = model_keys

        engines[key] = engine_record

    return engines, models


def _add_model_records(
    records: dict[str, dict[str, Any]],
    engine: str,
    declared_models: Any,
) -> list[str]:
    """Add an engine's model aliases to the global models registry.

    Runtime plans store the alias (for example ``cheap``), while ``model`` is
    the provider-facing model identifier resolved by the engine.
    """
    if not isinstance(declared_models, dict):
        return []

    keys: list[str] = []
    for alias, provider_model in declared_models.items():
        if not isinstance(alias, str) or not isinstance(provider_model, str):
            raise TypeError(f"{engine} model declarations must map strings to strings")

        registry_key = f"{engine}.{alias}"
        records[registry_key] = {
            "key": alias,
            "label": f"{_title(alias)} — {provider_model}",
            "engine": engine,
            "model": provider_model,
        }
        keys.append(registry_key)
    return keys


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
    """Resolve simple top-level constants without importing the extension.

    Supports both normal and annotated assignments, plus references from one
    constant to another, such as ``ENGINE_COMPONENT = {"models": MODEL_LABELS}``.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError):
        return {}

    metadata: dict[str, Any] = {}
    for node in tree.body:
        name: str | None = None
        value_node: ast.expr | None = None

        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                name = target.id
                value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = node.target.id
            value_node = node.value

        if name is None or value_node is None:
            continue

        try:
            metadata[name] = _literal_value(value_node, metadata)
        except (KeyError, TypeError, ValueError):
            continue

    return metadata


def _literal_value(node: ast.AST, names: dict[str, Any]) -> Any:
    if isinstance(node, ast.Name):
        return names[node.id]
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Dict):
        return {
            _literal_value(key, names): _literal_value(value, names)
            for key, value in zip(node.keys, node.values, strict=True)
            if key is not None
        }
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values = [_literal_value(item, names) for item in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(values)
        if isinstance(node, ast.Set):
            return set(values)
        return values
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _literal_value(node.operand, names)
        if not isinstance(value, (int, float, complex)):
            raise TypeError("unary operators require numeric literals")
        return value if isinstance(node.op, ast.UAdd) else -value
    raise ValueError(f"unsupported metadata expression: {type(node).__name__}")


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
