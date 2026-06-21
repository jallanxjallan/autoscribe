from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class UploadedItem:
    target: str
    slug: str
    key: str


@dataclass(frozen=True, slots=True)
class SkippedUpload:
    target: str
    location: str
    identifier: str
    error: str


@dataclass(frozen=True, slots=True)
class UploadReport:
    record_count: int = 0
    skipped_count: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    records: tuple[UploadedItem, ...] = ()
    skipped: tuple[SkippedUpload, ...] = ()


__all__ = ["SkippedUpload", "UploadedItem", "UploadReport"]
