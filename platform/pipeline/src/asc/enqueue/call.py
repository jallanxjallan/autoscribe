from asc.models.process.call import CallRecord
from asc.redis.key import RedisKey
from asc.state.slugmap import SlugMap


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


__all__ = ["load_call"]
