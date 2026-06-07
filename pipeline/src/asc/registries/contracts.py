from __future__ import annotations

import importlib
import inspect
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

try:
    from pydantic_core import PydanticUndefined
except ImportError:  # pragma: no cover
    PydanticUndefined = object()


class ContractResolutionError(ValueError):
    """Raised when a contract alias or model import path cannot be resolved."""


@dataclass(frozen=True)
class ModelContractRef:
    group: str
    name: str
    import_paths: tuple[str, ...]
    purpose: str = ""


MODEL_CONTRACTS: dict[str, ModelContractRef] = {
    "input:prompt": ModelContractRef(
        group="input",
        name="prompt",
        import_paths=(
            "asc.models.uploaded.record.UploadedRecord",
            "asc.models.uploaded.prompt.PromptRecord",
        ),
        purpose="Typed prompt records consumed by enqueue.",
    ),
    "input:instruction": ModelContractRef(
        group="input",
        name="instruction",
        import_paths=("asc.models.control.instruction.InstructionRecord",),
        purpose="Typed instruction control records consumed by control upload.",
    ),
    "input:plan": ModelContractRef(
        group="input",
        name="plan",
        import_paths=("asc.models.control.plan.PlanRecord",),
        purpose="Typed plan control records consumed by control upload.",
    ),
    "runtime:call": ModelContractRef(
        group="runtime",
        name="call",
        import_paths=("asc.models.runtime.call.CallRecord",),
        purpose="Runtime call record materialized by enqueue.",
    ),
    "runtime:step": ModelContractRef(
        group="runtime",
        name="step",
        import_paths=("asc.models.runtime.step.RuntimeStepRecord",),
        purpose="Runtime atomic step record consumed by workers.",
    ),
    "runtime:content": ModelContractRef(
        group="runtime",
        name="content",
        import_paths=("asc.models.runtime.content.RuntimeContentRecord",),
        purpose="Runtime content record consumed and produced by workers.",
    ),
    "export:pending-export": ModelContractRef(
        group="export",
        name="pending-export",
        import_paths=("asc.models.export.records.PendingExportRecord",),
        purpose="Typed rows emitted by pending export listing.",
    ),
    "export:extracted-result": ModelContractRef(
        group="export",
        name="extracted-result",
        import_paths=("asc.models.export.records.ExtractedResultRecord",),
        purpose="Typed rows emitted by export result extraction.",
    ),
    "export:export-update": ModelContractRef(
        group="export",
        name="export-update",
        import_paths=("asc.models.export.records.ExportUpdateRecord",),
        purpose="Typed records consumed when marking results exported.",
    ),
}

CONTRACT_ALIASES: dict[str, str] = {
    "export:pending": "export:pending-export",
    "export:update": "export:export-update",
}


def available_contracts() -> dict[str, dict[str, Any]]:
    return {
        key: {
            "group": ref.group,
            "name": ref.name,
            "purpose": ref.purpose,
            "import_paths": list(ref.import_paths),
        }
        for key, ref in sorted(MODEL_CONTRACTS.items())
    }


def canonical_contract_ref(model_ref: str) -> str:
    return CONTRACT_ALIASES.get(model_ref, model_ref)


def import_object(import_path: str) -> Any:
    if ":" in import_path:
        module_name, object_name = import_path.split(":", 1)
    else:
        try:
            module_name, object_name = import_path.rsplit(".", 1)
        except ValueError as exc:
            raise ContractResolutionError(
                f"not a valid import path: {import_path}"
            ) from exc

    module = importlib.import_module(module_name)
    return getattr(module, object_name)


def resolve_model(model_ref: str) -> type[BaseModel]:
    canonical_ref = canonical_contract_ref(model_ref)

    candidate_paths: Iterable[str]
    if canonical_ref in MODEL_CONTRACTS:
        candidate_paths = MODEL_CONTRACTS[canonical_ref].import_paths
    else:
        candidate_paths = (canonical_ref,)

    errors: list[str] = []
    for import_path in candidate_paths:
        try:
            obj = import_object(import_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{import_path}: {exc}")
            continue

        if not inspect.isclass(obj) or not issubclass(obj, BaseModel):
            errors.append(f"{import_path}: object is not a Pydantic BaseModel")
            continue

        return obj

    raise ContractResolutionError(
        "could not resolve model contract:\n  " + "\n  ".join(errors)
    )


def annotation_to_string(annotation: Any) -> str:
    if annotation is None:
        return "Any"

    text = getattr(annotation, "__name__", None)
    if text:
        return text

    return str(annotation).replace("typing.", "")


def alias_item_to_string(value: Any) -> str:
    if isinstance(value, str):
        return value

    path = getattr(value, "path", None)
    if path is not None:
        return ".".join(str(part) for part in path)

    return str(value)


def validation_aliases(field_info: Any) -> list[str]:
    alias = getattr(field_info, "validation_alias", None)

    if alias is None:
        field_alias = getattr(field_info, "alias", None)
        return [field_alias] if field_alias else []

    choices = getattr(alias, "choices", None)
    if choices is not None:
        return [alias_item_to_string(choice) for choice in choices]

    return [alias_item_to_string(alias)]


def input_names_for_field(field_name: str, field_info: Any) -> tuple[str, ...]:
    names: list[str] = [field_name]

    field_alias = getattr(field_info, "alias", None)
    if field_alias:
        names.append(field_alias)

    names.extend(validation_aliases(field_info))

    seen: set[str] = set()
    unique: list[str] = []

    for name in names:
        if name and name not in seen:
            seen.add(name)
            unique.append(name)

    return tuple(unique)


def default_to_string(field_info: Any) -> str | None:
    if field_info.is_required():
        return None

    default = getattr(field_info, "default", PydanticUndefined)
    if default is not PydanticUndefined:
        return repr(default)

    default_factory = getattr(field_info, "default_factory", None)
    if default_factory is not None:
        name = getattr(default_factory, "__name__", repr(default_factory))
        return f"{name}()"

    return None


def contract_for_model(
    model_type: type[BaseModel],
    *,
    alias: str | None = None,
    purpose: str = "",
) -> dict[str, Any]:
    config = getattr(model_type, "model_config", {}) or {}

    fields: list[dict[str, Any]] = []
    for name, field_info in model_type.model_fields.items():
        fields.append(
            {
                "name": name,
                "required": field_info.is_required(),
                "annotation": annotation_to_string(
                    getattr(field_info, "annotation", None)
                ),
                "input_names": list(input_names_for_field(name, field_info)),
                "serialization_alias": getattr(
                    field_info,
                    "serialization_alias",
                    None,
                ),
                "default": default_to_string(field_info),
                "description": getattr(field_info, "description", None),
            }
        )

    return {
        "alias": alias,
        "purpose": purpose,
        "model": model_type.__name__,
        "import_path": f"{model_type.__module__}.{model_type.__name__}",
        "extra": config.get("extra", "ignore"),
        "fields": fields,
    }


def contract_for_ref(model_ref: str) -> dict[str, Any]:
    canonical_ref = canonical_contract_ref(model_ref)
    model_type = resolve_model(canonical_ref)

    ref = MODEL_CONTRACTS.get(canonical_ref)
    return contract_for_model(
        model_type,
        alias=canonical_ref,
        purpose=ref.purpose if ref else "",
    )


def contracts_for_group(group: str) -> dict[str, dict[str, Any]]:
    return {
        key: contract_for_ref(key)
        for key, ref in sorted(MODEL_CONTRACTS.items())
        if ref.group == group
    }


def format_contract_text(contract: Mapping[str, Any]) -> str:
    required = [field for field in contract["fields"] if field["required"]]
    optional = [field for field in contract["fields"] if not field["required"]]

    lines: list[str] = []

    if contract.get("alias"):
        lines.append(f"Alias: {contract['alias']}")

    lines.extend(
        [
            f"Model: {contract['model']}",
            f"Import: {contract['import_path']}",
            f"Extra fields: {contract['extra']}",
        ]
    )

    if contract.get("purpose"):
        lines.append(f"Purpose: {contract['purpose']}")

    lines.append("")

    def append_field_group(title: str, fields: list[Mapping[str, Any]]) -> None:
        lines.append(f"{title}:")
        if not fields:
            lines.append("  none")
            lines.append("")
            return

        for field in fields:
            input_names = field.get("input_names", [])
            alias_text = ""

            if input_names and input_names != [field["name"]]:
                alias_text = f"  input={input_names}"

            output_name = field.get("serialization_alias")
            output_text = f"  output={output_name}" if output_name else ""

            default_value = field.get("default")
            default_text = (
                f"  default={default_value}"
                if default_value is not None
                else ""
            )

            lines.append(
                f"  {field['name']:<24} {field['annotation']}"
                f"{alias_text}{output_text}{default_text}"
            )

            if field.get("description"):
                lines.append(f"    {field['description']}")

        lines.append("")

    append_field_group("Required", required)
    append_field_group("Optional", optional)

    return "\n".join(lines).rstrip()


__all__ = [
    "CONTRACT_ALIASES",
    "MODEL_CONTRACTS",
    "ContractResolutionError",
    "ModelContractRef",
    "annotation_to_string",
    "available_contracts",
    "canonical_contract_ref",
    "contract_for_model",
    "contract_for_ref",
    "format_contract_text",
    "contracts_for_group",
    "import_object",
    "input_names_for_field",
    "resolve_model",
]
