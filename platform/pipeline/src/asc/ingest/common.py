from dataclasses import dataclass, field


class IngestInputError(ValueError):
    """Expected malformed or invalid upload input."""


@dataclass(frozen=True, slots=True)
class IngestedItem:
    record_type: str
    slug: str
    key: str


@dataclass(frozen=True, slots=True)
class SkippedIngest:
    record_type: str
    location: str
    identifier: str
    error: str


@dataclass(frozen=True, slots=True)
class IngestReport:
    record_count: int = 0
    skipped_count: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    records: tuple[IngestedItem, ...] = ()
    skipped: tuple[SkippedIngest, ...] = ()


__all__ = ["IngestInputError", "IngestReport", "IngestedItem", "SkippedIngest"]
