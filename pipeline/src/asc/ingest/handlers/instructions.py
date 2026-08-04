from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from asc.core.identity import generate_identity
from asc.models.control.instruction import Instruction
from asc.state.slugmap import SlugMap
from asc.ingest.common import IngestedItem, IngestInputError
from asc.ingest.expiry import expire_old_key
from asc.state.publications import bind as bind_publication

INSTRUCTION_TTL_SECONDS = 60 * 60 * 24 * 30


def ingest_instruction(record: Mapping[str, Any]) -> IngestedItem:
    slug = str(record["identity"]).strip()
    content = record["content"]
    extra = dict(record["extra"])
    publication_ulid = str(extra.get("publication_ulid") or "").strip()
    if not publication_ulid:
        raise IngestInputError("instruction publication_ulid is required")
    if not isinstance(content, str) or not content.strip():
        raise IngestInputError("instruction content must be a non-empty string")
    try:
        instruction = Instruction.model_validate({"identity": generate_identity(), "slug": slug, "content": content, "extra_json": extra})
    except ValidationError as exc:
        raise IngestInputError(f"validation failed: {exc}") from exc
    slugmap = SlugMap()
    old_key = slugmap.get(slug)
    new_key = str(instruction.save(ttl=INSTRUCTION_TTL_SECONDS))
    slugmap.set(slug, new_key)
    bind_publication(kind="instruction", slug=slug, publication_ulid=publication_ulid, record_key=new_key)
    expire_old_key(old_key, new_key)
    return IngestedItem(record_type="instruction", slug=slug, key=new_key)


__all__ = ["INSTRUCTION_TTL_SECONDS", "ingest_instruction"]
