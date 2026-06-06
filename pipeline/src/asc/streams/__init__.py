from __future__ import annotations

from asc.streams.emit import (
    emit_mapping,
    emit_model,
    emit_models,
    model_to_stream_record,
)
from asc.streams.ndjson import (
    NdjsonParseError,
    ParsedNdjsonLine,
    dump_ndjson_record,
    iter_ndjson_records,
    write_ndjson_record,
    write_ndjson_records,
)
from asc.streams.parser import (
    RAW_RECORD_FIELD,
    ParsedStreamRecord,
    flatten_mapping,
    iter_flat_stream_records,
    prepare_stream_record,
)
from asc.streams.upload_normalizer import (
    IdentifierClassification,
    IdentifierKind,
    JsonRecord,
    UploadRecordError,
    classify_identifier,
    parse_json_object_line,
    prepare_upload_record,
    require_identifier,
    require_record_type,
    require_top_level_text,
)

__all__ = [
    "model_to_stream_record",
    "emit_models",
    "emit_model",
    "emit_mapping",
    "NdjsonParseError",
    "ParsedNdjsonLine",
    "ParsedStreamRecord",
    "RAW_RECORD_FIELD",
    "dump_ndjson_record",
    "flatten_mapping",
    "iter_flat_stream_records",
    "iter_ndjson_records",
    "prepare_stream_record",
    "write_ndjson_record",
    "write_ndjson_records",
    "IdentifierClassification",
    "IdentifierKind",
    "JsonRecord",
    "UploadRecordError",
    "classify_identifier",
    "parse_json_object_line",
    "prepare_upload_record",
    "require_identifier",
    "require_record_type",
    "require_top_level_text",
]
