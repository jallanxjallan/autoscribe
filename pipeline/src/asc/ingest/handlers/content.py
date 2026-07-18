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
    payload = dict(record["payload"])
    payload.pop("identity", None)

    plan_slug = record.get("record_plan")
    if not isinstance(plan_slug, str) or not plan_slug.strip():
        raise IngestInputError("content record_plan must be a non-empty string")

    plan_key = SlugMap().get(plan_slug.strip())
    if not plan_key:
        raise IngestInputError(f"unknown record_plan: {plan_slug!r}")

    payload.update(
        identity=generate_identity(),
        source_identity=slug,
        plan_key=plan_key,
    )

    try:
        content = CallRecord.model_validate(payload)
    except ValidationError as exc:
        raise IngestInputError(f"validation failed: {exc}") from exc

    slugmap = SlugMap()
    old_key = slugmap.get(slug)
    new_key = str(content.save())

    slugmap.set(slug, new_key)
    expire_old_key(old_key, new_key)

    return IngestedItem(record_type="content", slug=slug, key=new_key)


__all__ = ["ingest_content"]
