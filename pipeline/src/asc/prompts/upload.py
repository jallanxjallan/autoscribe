from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import sys
from typing import TextIO

from asc.models.uploaded.record import UploadedRecord
from asc.prompts.reader import iter_uploaded_prompt_records

try:  # Current name after the prompt/control slugmap merge.
    from asc.state.slugmap import SlugMap
except ModuleNotFoundError:  # Compatibility with the pre-merge state package.
    from asc.state.control_slugmap import ControlSlugMap as SlugMap  # type: ignore[no-redef]


@dataclass(frozen=True, slots=True)
class UploadedPrompt:
    slug: str
    key: str


@dataclass(frozen=True, slots=True)
class PromptUploadReport:
    records: tuple[UploadedPrompt, ...]
    skipped: tuple[str, ...] = ()

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    @property
    def prompt_count(self) -> int:
        return len(self.records)

    @property
    def prompts(self) -> tuple[str, ...]:
        return tuple(record.slug for record in self.records)


def upload_prompts_stream(stream: TextIO) -> PromptUploadReport:
    return upload_prompt_records(iter_uploaded_prompt_records(stream))


def upload_prompt_records(records: Iterable[object]) -> PromptUploadReport:
    uploaded: list[UploadedPrompt] = []
    skipped: list[str] = []
    slugmap = SlugMap()

    for record_number, record in enumerate(records, start=1):
        try:
            uploaded.append(upload_prompt_record(record, slugmap=slugmap))
        except Exception as exc:
            identifier = _record_identifier(record, fallback=f"record {record_number}")
            skipped.append(identifier)
            print(f"[prompts:upload] {identifier}: skipped invalid prompt: {exc}", file=sys.stderr)
            continue

    return PromptUploadReport(records=tuple(uploaded), skipped=tuple(skipped))


def upload_prompt_record(record: object, *, slugmap: object | None = None) -> UploadedPrompt:
    prompt_record = _uploaded_record(record)
    slug = prompt_record.record_identity
    key = str(prompt_record.save())

    mapper = slugmap or SlugMap()
    _bind_record(mapper, prompt_record=prompt_record, key=key)
    return UploadedPrompt(slug=slug, key=key)


def _uploaded_record(record: object) -> UploadedRecord:
    if isinstance(record, UploadedRecord):
        return record
    return UploadedRecord.model_validate(record)


def _record_identifier(record: object, *, fallback: str) -> str:
    if isinstance(record, UploadedRecord):
        return record.record_identity

    if isinstance(record, Mapping):
        for field in ("record_identity", "prompt_slug", "slug", "identifier"):
            value = record.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()

    model_dump = getattr(record, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return _record_identifier(dumped, fallback=fallback)

    return fallback


def _bind_record(slugmap: object, *, prompt_record: UploadedRecord, key: str) -> None:
    bind_record = getattr(slugmap, "bind_record", None)
    if callable(bind_record):
        bind_record(prompt_record, full_key=key)
        return

    slug = prompt_record.record_identity
    for method_name in ("bind_key", "set_key", "write_key", "save_key"):
        method = getattr(slugmap, method_name, None)
        if callable(method):
            try:
                method(slug, key, kind="prompt")
            except TypeError:
                method(slug, key)
            return

    raise TypeError(
        "SlugMap must provide bind_record(), bind_key(), set_key(), write_key(), or save_key()"
    )


__all__ = [
    "PromptUploadReport",
    "UploadedPrompt",
    "upload_prompt_record",
    "upload_prompt_records",
    "upload_prompts_stream",
]
