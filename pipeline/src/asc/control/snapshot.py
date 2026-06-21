from typing import Any

from asc.redis.key import RedisKey
from asc.state.slugmap import SlugMap

CONTROL_KIND_TO_REGISTRY = {
    "instruction": "instructions",
    "plan": "plans",
}


def build_control_snapshot() -> dict[str, Any]:
    """
    Emit a live snapshot of uploaded controls from the control slugmap.

    Controls are mutable uploaded state, not immutable runtime registry entries.
    This snapshot reads the live slug -> Redis key index, removes stale pointers,
    and groups the current records by control kind.
    """
    slugmap = SlugMap()
    registries: dict[str, dict[str, Any]] = {
        name: {} for name in CONTROL_KIND_TO_REGISTRY.values()
    }
    stale: dict[str, str] = {}

    for slug, full_key in slugmap.list().items():
        key = RedisKey(full_key)
        if not key.exists():
            slugmap.delete(slug)
            stale[slug] = full_key
            continue

        kind = key.kind
        registry_name = CONTROL_KIND_TO_REGISTRY.get(kind)
        if registry_name is None:
            continue

        record = _snapshot_record(slug=slug, key=key, kind=kind)
        registries[registry_name][slug] = record

    return {
        "schema_version": 1,
        "type": "autoscribe.controls",
        "source": {
            "slugmap": SlugMap.KEY,
        },
        "registries": registries,
        "stale": stale,
    }


def _snapshot_record(*, slug: str, key: RedisKey, kind: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": kind,
        "slug": slug,
        "key": str(key),
    }

    identity = _identity_from_key(key)
    if identity:
        record["identity"] = identity

    # stored = key.hgetall()
    # if isinstance(stored, dict):
    #     label = _first_text(stored, "label", "title", "name")
    #     description = _first_text(stored, "description")
    #     if label:
    #         record["label"] = label
    #     if description:
    #         record["description"] = description

    return record


def _identity_from_key(key: RedisKey) -> str:
    return key.identity


def _first_text(source: dict[str, Any], *fields: str) -> str:
    for field in fields:
        value = source.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


__all__ = ["build_control_snapshot"]
