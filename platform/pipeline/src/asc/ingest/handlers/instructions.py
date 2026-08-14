from collections.abc import Mapping
from typing import Any
import hashlib

from pydantic import ValidationError

from asc.core.content_version import instruction_version_identity
from asc.models.control.instruction import Instruction
from asc.state.slugmap import SlugMap
from asc.ingest.common import IngestedItem, IngestInputError
from asc.ingest.expiry import expire_old_key

INSTRUCTION_TTL_SECONDS = 60 * 60 * 24 * 30


def ingest_instruction(record: Mapping[str, Any]) -> IngestedItem:
    slug = str(record["identity"]).strip()
    content = record["content"]
    extra = dict(record["extra"])
    title = str(extra.get("title") or slug).strip()
    if not isinstance(content, str) or not content.strip():
        raise IngestInputError("instruction content must be a non-empty string")
    try:
        instruction = Instruction.model_validate(
            {
                "identity": instruction_version_identity(slug, content),
                "slug": slug,
                "title": title,
                "content": content,
                "content_sha256": hashlib.sha256(content.strip().encode("utf-8")).hexdigest(),
                "source_modified_ns": int(extra.get("source_modified_ns") or 0),
                "source_size": int(extra.get("source_size") or 0),
                "extra_json": extra,
            }
        )
    except ValidationError as exc:
        raise IngestInputError(f"validation failed: {exc}") from exc
    slugmap = SlugMap()
    old_key = slugmap.get(slug)
    new_key = str(instruction.save(ttl=INSTRUCTION_TTL_SECONDS))
    slugmap.set(slug, new_key)
    expire_old_key(old_key, new_key)
    return IngestedItem(record_type="instruction", slug=slug, key=new_key)


__all__ = ["INSTRUCTION_TTL_SECONDS", "ingest_instruction"]
