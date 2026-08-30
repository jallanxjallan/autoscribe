from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from asc.core.identity import generate_identity
from asc.models.process.call import CallRecord
from asc.redis.key import RedisKey
from asc.state.slugmap import SlugMap

CALL_TTL_SECONDS = 60 * 60 * 24 * 30


def store_call(record: Mapping[str, Any]) -> tuple[str, CallRecord]:
    slug = _required_text(record.get("identity"), "identity")
    content = _required_text(record.get("content"), "content")
    extra = record.get("extra") or {}
    if not isinstance(extra, Mapping):
        raise TypeError("extra must be an object")
    try:
        call = CallRecord.model_validate({
            "identity": generate_identity(),
            "source_identity": slug,
            "content": content,
            "extra_json": dict(extra),
        })
    except ValidationError as exc:
        raise ValueError(f"call validation failed: {exc}") from exc

    slugmap = SlugMap()
    old_key = slugmap.get(slug)
    new_key = str(call.save(ttl=CALL_TTL_SECONDS))
    slugmap.set(slug, new_key)
    if old_key and old_key != new_key:
        RedisKey(old_key).delete()
    return new_key, call


def load_call(call_slug: str) -> tuple[str, CallRecord]:
    if not isinstance(call_slug, str) or not call_slug.strip():
        raise ValueError("call must be a non-empty slug")
    slug = call_slug.strip()
    resolved = SlugMap().get(slug)
    if not resolved:
        raise KeyError(f"missing slugmap entry for call: {slug}")
    key = RedisKey(str(resolved))
    if key.kind != "call":
        raise ValueError(f"call resolved to non-call key: {resolved}")
    if key.suffix in (None, "", "record"):
        record_key = str(RedisKey(kind="call", identity=key.identity, suffix="record"))
    else:
        raise ValueError(f"call resolved to non-record key: {resolved}")
    return record_key, CallRecord.load(record_key)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing required non-empty field: {field}")
    return value.strip()


__all__ = ["CALL_TTL_SECONDS", "load_call", "store_call"]
