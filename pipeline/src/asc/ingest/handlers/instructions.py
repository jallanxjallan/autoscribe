from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from asc.core.identity import generate_identity
from asc.models.control.instruction import Instruction
from asc.state.slugmap import SlugMap
from asc.ingest.common import IngestedItem
from asc.ingest.expiry import expire_old_key


def ingest_instruction(record: Mapping[str, Any]) -> IngestedItem:
    slug = str(record["record_identity"]).strip()

    try:
        instruction = Instruction.from_ndjson(record, identity=generate_identity())
    except ValidationError as exc:
        raise ValueError(f"validation failed: {exc}") from exc

    slugmap = SlugMap()
    old_key = slugmap.get(slug)
    new_key = str(instruction.save())

    slugmap.set(slug, new_key)
    expire_old_key(old_key, new_key)

    return IngestedItem(record_type="instruction", slug=slug, key=new_key)


__all__ = ["ingest_instruction"]
