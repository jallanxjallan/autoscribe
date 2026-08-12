from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from asc.core.identity import generate_identity
from asc.models.process.call import CallRecord
from asc.state.slugmap import SlugMap
from asc.ingest.common import IngestedItem, IngestInputError
from asc.ingest.expiry import expire_old_key

CALL_TTL_SECONDS = 60 * 60 * 24 * 30


def ingest_content(record: Mapping[str, Any]) -> IngestedItem:
    slug = str(record["identity"]).strip()
    content = record["content"]
    if not isinstance(content, str) or not content.strip():
        raise IngestInputError("call content must be a non-empty string")

    try:
        call = CallRecord.model_validate({
            "identity": generate_identity(),
            "source_identity": slug,
            "content": content,
            "extra_json": dict(record["extra"]),
        })
    except ValidationError as exc:
        raise IngestInputError(f"validation failed: {exc}") from exc

    slugmap = SlugMap()
    old_key = slugmap.get(slug)
    new_key = str(call.save(ttl=CALL_TTL_SECONDS))
    slugmap.set(slug, new_key)
    expire_old_key(old_key, new_key)
    return IngestedItem(record_type="content", slug=slug, key=new_key)


__all__ = ["CALL_TTL_SECONDS", "ingest_content"]
