import json
from typing import TextIO


def write_ndjson_record(record: object, sink: TextIO) -> None:
    json.dump(record, sink, ensure_ascii=False, separators=(",", ":"))
    sink.write("\n")
