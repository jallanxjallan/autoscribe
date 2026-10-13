from __future__ import annotations

import hashlib
import json
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .control import materialize_plan
from .ids import new_ulid
import unicodedata
from .ledger import record_call, ensure_schema, connect
from .redis_runtime import RedisClient, FORENSIC_TTL, EXECUTOR_QUEUE_KEY

INPUT_SCHEMA = "autoscribe.input.v1"
CALL_SCHEMA = "autoscribe.call-content.v2"


class EnqueueError(RuntimeError):
    pass


@dataclass(frozen=True)
class EnqueueResult:
    record_id: str
    call_id: str
    created: bool
    content_key: str
    baggage_key: str


def _required_text(record: dict, key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise EnqueueError(f"input {key} must be non-empty text")
    return value


def validate_input_record(record: dict) -> tuple[str, str]:
    if not isinstance(record, dict):
        raise EnqueueError("input record must be an object")
    if record.get("schema") not in (INPUT_SCHEMA, "autoscribe.input.v2"):
        raise EnqueueError(f"unsupported input schema: {record.get('schema')!r}")

    record_id = _required_text(record, "record_id")
    content = _required_text(record, "content")
    content_sha256 = _required_text(record, "content_sha256")
    actual_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if content_sha256 != actual_sha256:
        raise EnqueueError("input content_sha256 does not match content")

    source = record.get("source")
    routing = record.get("routing")
    baggage = record.get("baggage")
    if not isinstance(source, dict):
        raise EnqueueError("input source must be an object")
    if not isinstance(routing, dict):
        raise EnqueueError("input routing must be an object")
    if not isinstance(baggage, dict):
        raise EnqueueError("input baggage must be an object")

    plan_id = routing.get("plan_id")
    if not isinstance(plan_id, str) or not plan_id.startswith("pln_"):
        raise EnqueueError("routing.plan_id must be a pln_ identity")
    if record["schema"] == "autoscribe.input.v2":
        validate_parsed_input(record)
    return record_id, plan_id


def _relative(value: object) -> str:
    if (not isinstance(value, str) or not value or any(c in value for c in "\\:")
            or any(unicodedata.category(c) == "Cc" for c in value)
            or any(p in ("", ".", "..") or p.lower() == ".git" for p in value.split("/"))):
        raise EnqueueError("unsafe package path")
    return value


def _digest(value: object) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise EnqueueError("invalid SHA-256")


def validate_parsed_input(record: dict) -> None:
    if record.get("content_format") != "markdown" or record.get("directive_policy") != "inline.v1":
        raise EnqueueError("unsupported content format or directive policy")
    source = record["source"]
    client = record["baggage"].get("client")
    if not isinstance(client, dict) or source.get("kind") != "obsidian":
        raise EnqueueError("parsed source requires Obsidian client identity")
    _relative(source.get("path"))
    _digest(source.get("vault_id"))
    slug = source.get("slug")
    if not isinstance(slug, str) or not slug.strip():
        raise EnqueueError("source requires slug")
    if client.get("source_slug") != slug or client.get("source_path") != source["path"] or client.get("vault_id") != source["vault_id"]:
        raise EnqueueError("source/baggage identity mismatch")
    _digest(client.get("source_body_sha256"))
    if not isinstance(client.get("frontmatter"), str) or not client["frontmatter"]:
        raise EnqueueError("opaque frontmatter required for writeback")
    refs = record.get("references")
    assets = record.get("assets")
    if not isinstance(refs, list) or not isinstance(assets, list):
        raise EnqueueError("references and assets must be arrays")
    seen = set()
    for ref in refs:
        if not isinstance(ref, dict): raise EnqueueError("reference must be an object")
        path = _relative(ref.get("path"))
        if path in seen: raise EnqueueError("duplicate source reference")
        seen.add(path)
        if not isinstance(ref.get("slug"), str) or not ref["slug"]:
            raise EnqueueError("reference requires slug")
        _digest(ref.get("content_sha256"))
    if not any(ref.get("path") == source["path"] and ref.get("slug") == slug
               and ref.get("content_sha256") == client["source_body_sha256"] for ref in refs):
        raise EnqueueError("root source reference identity/checksum mismatch")
    seen = set()
    total = 0
    for asset in assets:
        if not isinstance(asset, dict): raise EnqueueError("asset must be an object")
        path = _relative(asset.get("path"))
        if (not path.startswith("assets/") or path.lower() in seen
                or any(path.lower().startswith(p + "/") or p.startswith(path.lower() + "/") for p in seen)):
            raise EnqueueError("asset requires unique assets/ path")
        seen.add(path.lower())
        data = asset.get("content_hex")
        if not isinstance(data, str) or not data or len(data) > 2097152 or any(c not in "0123456789abcdefABCDEF" for c in data):
            raise EnqueueError("invalid or oversized asset hex")
        try: raw = bytes.fromhex(data)
        except ValueError as exc: raise EnqueueError("invalid asset hex") from exc
        total += len(raw)
        if total > 1048576: raise EnqueueError("package assets exceed body limit")
        if hashlib.sha256(raw).hexdigest() != asset.get("sha256"):
            raise EnqueueError("asset checksum mismatch")


def build_call_content(record: dict, plan: dict) -> dict:
    result = {
        "schema": CALL_SCHEMA,
        "record_id": record["record_id"],
        "source": record["source"],
        "routing": record["routing"],
        "input": {
            "content": record["content"],
            "content_sha256": record["content_sha256"],
        },
        "plan": plan,
    }

    if record["schema"] == "autoscribe.input.v2":
        for key in ("content_format", "directive_policy", "references", "assets"):
            result["input"][key] = record[key]
    return result


def enqueue_record(
    *,
    record: dict,
    control_db: Path,
    ledger_db: Path,
    client: RedisClient,
    queue: bool = True,
) -> EnqueueResult:
    record_id, plan_id = validate_input_record(record)
    # Reserve a durable identity BEFORE touching Redis. A retry after a crash
    # must address the same call even if its queue member was already consumed.
    logical_record = dict(record)
    if record["schema"] == INPUT_SCHEMA and record["source"].get("kind") == "dropbox_ndjson":
        logical_record["source"] = {k: v for k, v in record["source"].items()
                                    if k not in ("transport_file", "line")}
    fingerprint = hashlib.sha256(json.dumps(logical_record, sort_keys=True,
        ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    ensure_schema(ledger_db)
    with closing(connect(ledger_db)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS enqueue_inputs (
            record_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
            call_id TEXT NOT NULL UNIQUE, queued INTEGER NOT NULL DEFAULT 0)""")
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT fingerprint, call_id, queued FROM enqueue_inputs WHERE record_id = ?",
                         (record_id,)).fetchone()
        if row:
            if row["fingerprint"] != fingerprint:
                raise EnqueueError("record_id already belongs to different input")
            call_id = str(row["call_id"])
        else:
            call_id = new_ulid()
            db.execute("INSERT INTO enqueue_inputs (record_id, fingerprint, call_id) VALUES (?, ?, ?)",
                       (record_id, fingerprint, call_id))
    content_key = f"call:{call_id}:content"
    baggage_key = f"call:{call_id}:baggage"
    marker = f"enqueue:{call_id}"
    # Persistent receipt outlives the forensic content TTL and consumed queue.
    # Do not rewrite content or re-materialize a changed plan on completed retry.
    if (row and row["queued"]) or client.command("GET", marker) == fingerprint:
        return EnqueueResult(record_id, call_id, False, content_key, baggage_key)
    plan = materialize_plan(control_db, plan_id)
    content = build_call_content(record, plan)
    record_call(ledger_db, call_id, {"content": content_key, "baggage": baggage_key})
    created = client.command("EVAL", """
        local prior = redis.call('GET', KEYS[1])
        if prior then
            if prior ~= ARGV[1] then return redis.error_reply('enqueue collision') end
            return 0
        end
        redis.call('HSET', KEYS[2], 'json', ARGV[2])
        redis.call('EXPIRE', KEYS[2], ARGV[4])
        redis.call('HSET', KEYS[3], 'json', ARGV[3])
        redis.call('EXPIRE', KEYS[3], ARGV[4])
        if ARGV[6] == '1' then redis.call('ZADD', KEYS[4], 0, ARGV[5]) end
        redis.call('SET', KEYS[1], ARGV[1])
        return 1
        """, 4, marker, content_key, baggage_key, EXECUTOR_QUEUE_KEY,
        fingerprint, json.dumps(content, ensure_ascii=False),
        json.dumps(record["baggage"], ensure_ascii=False), FORENSIC_TTL, call_id, int(queue))
    with closing(connect(ledger_db)) as db, db:
        db.execute("UPDATE enqueue_inputs SET queued = 1 WHERE record_id = ?", (record_id,))
    return EnqueueResult(record_id, call_id, bool(created), content_key, baggage_key)
