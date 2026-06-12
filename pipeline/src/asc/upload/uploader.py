from __future__ import annotations

import importlib
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TextIO

from asc.redis.model_base import RedisModel
from asc.upload.common import (
    SkippedUpload,
    UploadedItem,
    UploadReport,
    UploadTarget,
    assert_trusted_upload_source,
    normalize_json_baggage,
    normalize_record_content_alias,
    normalize_record_identity_alias,
    normalize_record_type_alias,
    normalize_upload_record,
    record_identifier,
    record_identity,
    save_upload_record,
    validate_control_record,
    validate_typed_control_record,
    validate_upload_record,
)


@dataclass(frozen=True)
class UploadModuleSpec:
    canonical_name: str
    module_name: str
    aliases: tuple[str, ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        return (self.canonical_name, *self.aliases)


MODULE_SPECS: tuple[UploadModuleSpec, ...] = (
    UploadModuleSpec(
        canonical_name="instruction",
        module_name="asc.upload.instructions",
        aliases=("instructions",),
    ),
    UploadModuleSpec(
        canonical_name="call",
        module_name="asc.upload.calls",
        aliases=("calls", "document", "documents", "prompt", "prompts"),
    ),
    UploadModuleSpec(
        canonical_name="plan",
        module_name="asc.upload.plans",
        aliases=("plans",),
    ),
    UploadModuleSpec(
        canonical_name="asset",
        module_name="asc.upload.assets",
        aliases=("assets",),
    ),
)

MODULES_BY_NAME: dict[str, UploadModuleSpec] = {
    name: spec for spec in MODULE_SPECS for name in spec.names
}
ASSET_TARGET_NAMES = {"asset", "assets"}


def upload_stream(
    source: Iterable[str],
    *,
    target: str,
    error_stream: TextIO = sys.stderr,
) -> UploadReport:
    module = upload_module_for_name(target)
    return module.upload_stream(source, error_stream=error_stream)


def upload_records(
    records: Iterable[object],
    *,
    target: str,
    error_stream: TextIO = sys.stderr,
) -> UploadReport:
    module = upload_module_for_name(target)
    return module.upload_records(records, error_stream=error_stream)


def upload_instructions_stream(source: Iterable[str], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    return upload_stream(source, target="instructions", error_stream=error_stream)


def upload_plans_stream(source: Iterable[str], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    return upload_stream(source, target="plans", error_stream=error_stream)


def upload_calls_stream(source: Iterable[str], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    return upload_stream(source, target="calls", error_stream=error_stream)


def upload_assets_stream(source: Iterable[str], *, error_stream: TextIO = sys.stderr) -> UploadReport:
    return upload_stream(source, target="assets", error_stream=error_stream)


def upload_module_for_name(name: str):
    spec = upload_module_spec_for_name(name)
    return importlib.import_module(spec.module_name)


def upload_module_spec_for_name(name: str) -> UploadModuleSpec:
    normalized = normalize_target_name(name)
    spec = MODULES_BY_NAME.get(normalized)
    if spec is None:
        known = ", ".join(sorted(MODULES_BY_NAME))
        raise ValueError(f"unknown upload target {name!r}; known: {known}")
    return spec


def normalize_target_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def upload_target_for_name(name: str) -> UploadTarget:
    """Compatibility helper returning the lazily loaded target definition."""

    module = upload_module_for_name(name)
    target_factory = getattr(module, "target", None)
    if target_factory is None:
        raise NotImplementedError(f"upload target {name!r} does not expose a target definition")
    return target_factory()


def upload_target_for_record(record: RedisModel) -> UploadTarget:
    """Compatibility helper for tests/older callers.

    Avoid importing every model at module load time. We inspect by package/name
    and then import only the matching uploader module.
    """

    module_name = type(record).__module__
    class_name = type(record).__name__

    if module_name.endswith(".instruction") and class_name == "InstructionRecord":
        return upload_target_for_name("instruction")
    if module_name.endswith(".plan") and class_name == "PlanRecord":
        return upload_target_for_name("plan")
    if module_name.endswith(".call") and class_name == "CallRecord":
        return upload_target_for_name("call")
    raise TypeError(f"unsupported upload record model: {type(record).__name__}")


# Compatibility aliases for older callers/tests.
def upload_typed_control_stream(
    source: Iterable[str],
    *,
    target: str,
    error_stream: TextIO = sys.stderr,
) -> UploadReport:
    return upload_stream(source, target=target, error_stream=error_stream)


def save_control_record(record: RedisModel) -> None:
    target = upload_target_for_record(record)
    save_upload_record(record, target=target)


def control_model_for_target(target: str):
    upload_target = upload_target_for_name(target)
    if upload_target.name not in {"instruction", "plan"}:
        known = "instruction, instructions, plan, plans"
        raise ValueError(f"unknown control upload target {target!r}; known: {known}")
    return upload_target.name, upload_target.model_type


CONTROL_TARGETS: dict[str, str] = {
    "instructions": "instruction",
    "plans": "plan",
    "instruction": "instruction",
    "plan": "plan",
}


def _control_models() -> dict[str, type[RedisModel]]:
    return {
        "instruction": upload_target_for_name("instruction").model_type,
        "plan": upload_target_for_name("plan").model_type,
    }


class _LazyControlModels(dict[str, type[RedisModel]]):
    def __getitem__(self, key: str) -> type[RedisModel]:
        return _control_models()[key]

    def get(self, key: str, default=None):
        return _control_models().get(key, default)

    def keys(self):
        return _control_models().keys()

    def items(self):
        return _control_models().items()

    def values(self):
        return _control_models().values()

    def __iter__(self):
        return iter(_control_models())

    def __len__(self) -> int:
        return len(_control_models())


CONTROL_MODELS: dict[str, type[RedisModel]] = _LazyControlModels()


__all__ = [
    "ASSET_TARGET_NAMES",
    "CONTROL_MODELS",
    "CONTROL_TARGETS",
    "MODULE_SPECS",
    "MODULES_BY_NAME",
    "SkippedUpload",
    "UploadedItem",
    "UploadModuleSpec",
    "UploadReport",
    "UploadTarget",
    "assert_trusted_upload_source",
    "control_model_for_target",
    "normalize_json_baggage",
    "normalize_record_content_alias",
    "normalize_record_identity_alias",
    "normalize_record_type_alias",
    "normalize_target_name",
    "normalize_upload_record",
    "record_identifier",
    "record_identity",
    "save_control_record",
    "save_upload_record",
    "upload_assets_stream",
    "upload_calls_stream",
    "upload_instructions_stream",
    "upload_module_for_name",
    "upload_module_spec_for_name",
    "upload_plans_stream",
    "upload_records",
    "upload_stream",
    "upload_target_for_name",
    "upload_target_for_record",
    "upload_typed_control_stream",
    "validate_control_record",
    "validate_typed_control_record",
    "validate_upload_record",
]
