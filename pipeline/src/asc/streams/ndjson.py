"""Compatibility imports for NDJSON stream helpers.

The canonical implementation now lives in ``asc.streams.parser`` because the
reader/parser boundary is small and generic. Keep this module so older callers
such as control uploaders can continue importing ``asc.streams.ndjson`` while
call sites are migrated gradually.
"""

from asc.streams.parser import (
    NdjsonParseError,
    ParsedNdjsonLine,
    dump_ndjson_record,
    iter_ndjson_records,
    write_ndjson_record,
    write_ndjson_records,
)

__all__ = [
    "NdjsonParseError",
    "ParsedNdjsonLine",
    "dump_ndjson_record",
    "iter_ndjson_records",
    "write_ndjson_record",
    "write_ndjson_records",
]
