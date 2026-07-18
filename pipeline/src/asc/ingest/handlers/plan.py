from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from asc.models.control.plan import Plan
from asc.state.slugmap import SlugMap
from asc.ingest.common import IngestedItem, IngestInputError
from asc.ingest.expiry import expire_old_key

PLAN_TTL_SECONDS = 60 * 60 * 24 * 30


def ingest_plan(record: Mapping[str, Any]) -> IngestedItem:
    """Validate and save one reusable plan payload.

    Upload-envelope fields route the record. Only ``payload`` is used as plan
    data; ``record_identity`` is translated to the stored plan's ``slug``.
    """

    slug = str(record["record_identity"]).strip()
    payload = dict(record["payload"])
    payload.pop("identity", None)
    payload["slug"] = slug

    try:
        plan = Plan.model_validate(payload)
    except ValidationError as exc:
        raise IngestInputError(f"validation failed: {exc}") from exc

    if not plan.steps:
        raise IngestInputError("plan steps must not be empty")

    new_key = plan.save(ttl=PLAN_TTL_SECONDS)

    slugmap = SlugMap()
    old_key = slugmap.get(plan.slug)
    slugmap.set(plan.slug, new_key)
    expire_old_key(old_key, new_key)

    return IngestedItem(record_type="plan", slug=plan.slug, key=new_key)


__all__ = ["PLAN_TTL_SECONDS", "ingest_plan"]
