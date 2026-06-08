from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TextIO

from pydantic import BaseModel

from asc.streams.parser import write_ndjson_record


def model_to_stream_record(model: BaseModel) -> dict[str, Any]:
    """Return a model as a JSON-ready typed stream record."""
    return model.model_dump(mode="json")


def emit_model(model: BaseModel, stream: TextIO) -> None:
    """Write one Pydantic model as one NDJSON line."""
    write_ndjson_record(model_to_stream_record(model), stream)


def emit_models(models: Iterable[BaseModel], stream: TextIO) -> int:
    """Write Pydantic models as NDJSON and return the number emitted."""
    count = 0
    for model in models:
        emit_model(model, stream)
        count += 1
    return count


def emit_mapping(record: Mapping[str, Any], stream: TextIO) -> None:
    """Write one already-validated typed mapping as one NDJSON line."""
    write_ndjson_record(record, stream)


__all__ = [
    "emit_mapping",
    "emit_model",
    "emit_models",
    "model_to_stream_record",
]
