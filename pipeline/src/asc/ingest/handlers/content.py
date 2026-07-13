from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from asc.core.identity import generate_identity
from asc.models.process.call import CallRecord
from asc.state.slugmap import SlugMap
from asc.ingest.common import IngestedItem, IngestInputError
from asc.ingest.expiry import expire_old_key


def ingest_content(record: Mapping[str, Any]) -> IngestedItem:
    slug = str(record["record_identity"]).strip()
    data = dict(record)
    data.pop("identity", None)

    try:
        if hasattr(CallRecord, "from_ndjson"):
            content = CallRecord.from_ndjson(data, identity=generate_identity())
        else:
            content = CallRecord.model_validate(data)
    except ValidationError as exc:
        raise IngestInputError(f"validation failed: {exc}") from exc

    slugmap = SlugMap()
    old_key = slugmap.get(slug)
    new_key = str(content.save())

    slugmap.set(slug, new_key)
    expire_old_key(old_key, new_key)

    return IngestedItem(record_type="content", slug=slug, key=new_key)


__all__ = ["ingest_content"]
