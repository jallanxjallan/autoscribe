from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from asc.models.control.plan import Plan
from asc.state.slugmap import SlugMap
from asc.ingest.common import IngestedItem, IngestInputError
from asc.ingest.expiry import expire_old_key
from asc.state.publications import bind as bind_publication

PLAN_TTL_SECONDS = 60 * 60 * 24 * 30


def ingest_plan(record: Mapping[str, Any]) -> IngestedItem:
    slug = str(record["identity"]).strip()
    content = record["content"]
    extra = dict(record["extra"])
    publication_ulid = str(extra.get("publication_ulid") or content.get("publication_ulid") or "").strip()
    if not publication_ulid:
        raise IngestInputError("plan publication_ulid is required")
    if not isinstance(content, Mapping):
        raise IngestInputError("plan content must be an object")
    try:
        plan = Plan.from_content(content, slug=slug, extra=extra)
    except (ValidationError, TypeError, ValueError) as exc:
        raise IngestInputError(f"validation failed: {exc}") from exc
    if not plan.steps:
        raise IngestInputError("plan steps must not be empty")
    new_key = plan.save(ttl=PLAN_TTL_SECONDS)
    slugmap = SlugMap()
    old_key = slugmap.get(plan.slug)
    slugmap.set(plan.slug, new_key)
    bind_publication(kind="plan", slug=plan.slug, publication_ulid=publication_ulid, record_key=new_key)
    expire_old_key(old_key, new_key)
    return IngestedItem(record_type="plan", slug=plan.slug, key=new_key)


__all__ = ["PLAN_TTL_SECONDS", "ingest_plan"]
