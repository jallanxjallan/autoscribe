from __future__ import annotations

import hashlib
import json
import re
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .control import materialize_plan
from .ids import new_ulid
import unicodedata
from .ledger import record_call, record_response, ensure_schema, connect
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
    failure: str | None = None


def _required_text(record: dict, key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise EnqueueError(f"input {key} must be non-empty text")
    return value


def _failure(record: dict) -> str | None:
    if 'failure' not in record:
        return None
    value = record['failure']
    if not isinstance(value, str) or not value.strip():
        raise EnqueueError('failure must be nonempty text')
    return value


def validate_raw_input(record: dict) -> str:
    if any(key in record for key in ('content', 'failure')):
        raise EnqueueError('v3 accepts raw Markdown, not prepared content/failure')
    raw = record.get('raw_markdown')
    if not isinstance(raw, str):
        raise EnqueueError('raw_markdown must be text')
    try:
        data = raw.encode('utf-8')
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (UnicodeError, ValueError) as exc:
        raise EnqueueError('invalid UTF-8 document/envelope') from exc
    if len(data) > 1048576 or len(encoded) >= 2097152:
        raise EnqueueError('raw document/envelope exceeds transport limits')
    _digest(record.get('raw_markdown_sha256'))
    if hashlib.sha256(data).hexdigest() != record['raw_markdown_sha256']:
        raise EnqueueError('raw Markdown checksum mismatch')
    source, baggage = record.get('source'), record.get('baggage')
    if not isinstance(source, dict) or source.get('kind') != 'obsidian' or not isinstance(baggage, dict):
        raise EnqueueError('v3 requires source and baggage identities')
    _relative(source.get('path'))
    _digest(source.get('vault_id'))
    client = baggage.get('client')
    if not isinstance(client, dict):
        raise EnqueueError('missing client coordination metadata')
    _digest(client.get('source'))
    if (client.get('source_path') != source['path'] or client.get('vault_id') != source['vault_id']
            or client.get('raw_markdown_sha256') != record['raw_markdown_sha256']):
        raise EnqueueError('v3 source/client identity mismatch')
    if not isinstance(client.get('submission_id'), str) or not re.fullmatch(r'sub_[A-Za-z0-9_-]{1,150}', client['submission_id']):
        raise EnqueueError('invalid submission identity')
    identity = dict(record)
    record_id = identity.pop('record_id', None)
    expected = 'inp_' + hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()[:32]
    if record_id != expected:
        raise EnqueueError('v3 record_id does not identify the exact request payload')
    return record_id


def validate_input_record(record: dict) -> tuple[str, str | None]:
    if not isinstance(record, dict):
        raise EnqueueError("input record must be an object")
    if record.get("schema") == "autoscribe.input.v3":
        return validate_raw_input(record), None
    if record.get("schema") not in (INPUT_SCHEMA, "autoscribe.input.v2"):
        raise EnqueueError(f"unsupported input schema: {record.get('schema')!r}")

    record_id = _required_text(record, "record_id")
    failure = _failure(record)
    content = record.get('content')
    if not isinstance(content, str) or (not content and failure is None):
        raise EnqueueError('input content must be non-empty text unless failure is present')
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

    if record["schema"] in ("autoscribe.input.v2", "autoscribe.prepared.v1"):
        for key in ("content_format", "directive_policy", "references", "assets"):
            result["input"][key] = record[key]
    for key in ('failure', 'failure_reason'):
        if key in record:
            result[key] = record[key]
    for key in ('asset_references', 'staged_assets', 'directives', 'metadata'):
        if key in record:
            result['input'][key] = record[key]
    return result


def register_failure(ledger_db: Path, client: RedisClient, call_id: str, content: dict) -> str:
    from .worker import TaskResult, persist_redis_response
    failure = _failure(content)
    if failure is None:
        raise EnqueueError('terminal failure requires failure text')
    key = persist_redis_response(client, TaskResult('', call_id, 0, 'preprocessing',
        'pandoc', 'autoscribe-ingest-v1', failure))
    client.hset(key, {'status': 'failed', 'failure': failure,
                     'error': content.get('failure_reason', failure)})
    record_response(ledger_db, call_id, key)
    return key


def enqueue_record(
    *,
    record: dict,
    control_db: Path,
    ledger_db: Path,
    client: RedisClient,
    queue: bool = True,
    work_dir: Path | None = None,
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
    # Completed receipts bypass preprocessing/dependency/plan changes on replay.
    if row and row['queued']:
        outcome = client.hgetall(f'response:{call_id}:content')
        return EnqueueResult(record_id, call_id, False, content_key, baggage_key, outcome.get('failure'))
    # Reconcile the crash boundary after Redis materialization, before SQL receipt.
    from .redis_runtime import load_json
    prior_marker = client.command('GET', marker)
    if prior_marker is not None and prior_marker != fingerprint:
        raise EnqueueError('enqueue marker collision')
    if prior_marker == fingerprint:
        content = load_json(client, content_key)
        failure = _failure(content)
        if failure:
            register_failure(ledger_db, client, call_id, content)
        with closing(connect(ledger_db)) as db, db:
            db.execute('UPDATE enqueue_inputs SET queued = 1 WHERE record_id = ?', (record_id,))
        return EnqueueResult(record_id, call_id, False, content_key, baggage_key, failure)
    incoming = record
    if incoming['schema'] == 'autoscribe.input.v3':
        from .preprocess import prepare
        from .control import resolve_plan
        record = prepare(incoming)
        if not record.get('failure'):
            plan_id = record['routing']['plan_id']
            if resolve_plan(control_db, plan_id) is None:
                record.update(content='', content_sha256=hashlib.sha256(b'').hexdigest(),
                              failure='Unreadable', failure_reason='Unknown plan identity')
    failure = _failure(record)
    plan = {} if failure else materialize_plan(control_db, plan_id)
    if incoming['schema'] == 'autoscribe.input.v3' and not failure:
        from .assets import stage_assets
        record['staged_assets'] = stage_assets(record['asset_references'], work_dir)
    content = build_call_content(record, plan)
    record_call(ledger_db, call_id, {'content': content_key, 'baggage': baggage_key})
    created = client.command("EVAL", """
        local prior = redis.call('GET', KEYS[1])
        if prior then
            if prior ~= ARGV[1] then return redis.error_reply('enqueue collision') end
            return 0
        end
        redis.call('HSET', KEYS[2], 'json', ARGV[2])
        redis.call('PERSIST', KEYS[2])
        redis.call('HSET', KEYS[3], 'json', ARGV[3])
        redis.call('PERSIST', KEYS[3])
        if ARGV[6] == '1' then redis.call('ZADD', KEYS[4], 0, ARGV[5]) end
        redis.call('SET', KEYS[1], ARGV[1])
        return 1
        """, 4, marker, content_key, baggage_key, EXECUTOR_QUEUE_KEY,
        fingerprint, json.dumps(content, ensure_ascii=False),
        json.dumps(record["baggage"], ensure_ascii=False), FORENSIC_TTL, call_id, int(queue and not failure))
    if not created:
        # Concurrent submission uses the first materialized outcome, including
        # its failure disposition, rather than the losing local interpretation.
        content = load_json(client, content_key)
        failure = _failure(content)
    if failure:
        register_failure(ledger_db, client, call_id, content)
    with closing(connect(ledger_db)) as db, db:
        db.execute("UPDATE enqueue_inputs SET queued = 1 WHERE record_id = ?", (record_id,))
    return EnqueueResult(record_id, call_id, bool(created), content_key, baggage_key, failure)
