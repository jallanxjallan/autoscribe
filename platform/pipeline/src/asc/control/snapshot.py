"""Build the live control snapshot consumed by the client."""

from typing import Any

from asc.control.extensions import build_extension_catalog
from asc.redis.key import RedisKey
from asc.state.slugmap import SlugMap


CONTROL_KIND_TO_REGISTRY = {
    "instruction": "instructions",
    "plan": "plans",
}

# Instructions need only catalogue metadata. Plans are few and small, and the
# current client has no separate pipeline read command, so the control snapshot
# also carries the persisted plan definition required by Define Plan.
SNAPSHOT_FIELDS = {
    "instruction": (
        "record_identity",
        "title",
        "label",
        "content_sha256",
    ),
    "plan": (
        "record_identity",
        "label",
        "description",
        "total_steps",
        "created_at",
        "metadata_json",
        "steps_json",
    ),
}


def build_control_snapshot() -> dict[str, Any]:
    """Return a live catalog of uploaded plans and instructions.

    The slugmap is authoritative. Stale slug pointers are removed while the
    snapshot is built. Plan entries include their stored definition because the
    Define Plan client must be able to reopen them and there is currently no
    separate control-read command.
    """
    slugmap = SlugMap()
    registries: dict[str, dict[str, Any]] = {
        registry: {} for registry in CONTROL_KIND_TO_REGISTRY.values()
    }
    stale: dict[str, str] = {}

    for slug, full_key in slugmap.list().items():
        key = RedisKey(full_key)

        if not key.exists():
            slugmap.delete(slug)
            stale[slug] = full_key
            continue

        registry = CONTROL_KIND_TO_REGISTRY.get(key.kind)
        if registry is None:
            continue

        registries[registry][slug] = _snapshot_record(
            slug=slug,
            key=key,
            kind=key.kind,
        )

    extension_catalog = build_extension_catalog()
    extension_registries = extension_catalog.get("registries", {})

    return {
        "schema_version": 2,
        "type": "autoscribe.controls",
        "source": {
            "slugmap": SlugMap.KEY,
            "extensions": extension_catalog.get("sources", {}),
        },
        "registries": {
            **registries,
            "engines": dict(extension_registries.get("engines", {})),
            "models": dict(extension_registries.get("models", {})),
            "local_scripts": dict(extension_registries.get("local_scripts", {})),
            "rag_profiles": dict(extension_registries.get("rag_profiles", {})),
        },
        "stale": stale,
    }


def _snapshot_record(*, slug: str, key: RedisKey, kind: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "type": kind,
        "slug": slug,
        "key": str(key),
        "identity": key.identity,
        "ttl": key.ttl(),
    }

    for field in SNAPSHOT_FIELDS[kind]:
        value = _text_value(key.hget(field))
        if value:
            record[field] = value

    # Older records may not carry record_identity. The slug remains the public
    # control identity and is the correct fallback for client selection.
    record.setdefault("record_identity", slug)
    record.setdefault("title", slug)
    record.setdefault("label", record.get("title") or slug)
    return record


def _text_value(value: Any) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return str(value)


__all__ = ["build_control_snapshot"]
