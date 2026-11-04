from __future__ import annotations

import json
import socket
from contextlib import closing
from pathlib import Path
from typing import Iterator

from .ledger import connect, ensure_schema, load_response, pending_exports, record_export
from .redis_runtime import FORENSIC_TTL, RedisClient, load_json


class ExporterError(RuntimeError):
    pass


def pending_count(path: Path) -> int:
    return len(pending_exports(path))


def build_pending_record(client: RedisClient, *, call_id: str, baggage_key: str) -> dict:
    baggage = load_json(client, baggage_key)
    if not isinstance(baggage, dict):
        raise ExporterError(f"invalid baggage record: {baggage_key}")
    return {
        "schema": "autoscribe.export-pending.v1",
        "call_id": call_id,
        "baggage": baggage,
    }


def iter_pending_records(path: Path, client: RedisClient) -> Iterator[dict]:
    for row in pending_exports(path):
        yield build_pending_record(
            client,
            call_id=str(row["call_id"]),
            baggage_key=str(row["baggage_key"]),
        )


def iter_pending_ndjson(path: Path, client: RedisClient) -> Iterator[str]:
    # Keep records independent: one expired/corrupt baggage key must not hide every
    # other pending export from Responses.
    for row in pending_exports(path):
        call_id = str(row["call_id"])
        try:
            record = build_pending_record(
                client,
                call_id=call_id,
                baggage_key=str(row["baggage_key"]),
            )
        except Exception as exc:
            record = {
                "schema": "autoscribe.export-pending-error.v1",
                "call_id": call_id,
                "error": str(exc),
            }
        yield json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def response_content(path: Path, client: RedisClient, call_id: str) -> str:
    row = load_response(path, call_id)
    key = str(row["redis_key"])
    response = client.hgetall(key)
    if not response:
        raise ExporterError(f"missing response Redis hash: {key}")
    content = response.get("content")
    if content is None:
        raise ExporterError(f"response Redis hash has no content: {key}")
    return content


def poke_responses(path: Path, socket_path: Path) -> int:
    """Notify the legacy response coordinator that unexported rows exist."""
    count = pending_count(path)
    if count == 0:
        return 0
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.sendto(str(count).encode("ascii"), str(socket_path))
    except OSError as exc:
        raise ExporterError(f"could not notify Responses at {socket_path}: {exc}") from exc
    finally:
        sock.close()
    return count


def mark_exported(
    path: Path,
    client: RedisClient,
    *,
    call_id: str,
    receipt: dict,
) -> tuple[str, bool]:
    """Persist a legacy authenticated Rust receipt and corresponding SQLite fact."""
    if not isinstance(receipt, dict):
        raise ExporterError("export receipt is not an object")
    if receipt.get("schema") != "autoscribe.receipt.v1":
        raise ExporterError(f"invalid export receipt schema: {receipt.get('schema')!r}")

    fields = {}
    for field in ("effect_key", "kind", "target", "result"):
        value = receipt.get(field)
        if not isinstance(value, str) or not value:
            raise ExporterError(f"export receipt missing {field}")
        fields[field] = value

    key = f"export:{call_id}:receipt"
    client.hset(key, fields)
    client.expire(key, FORENSIC_TTL)
    created = record_export(path, call_id, key)
    retain_delivered(path, client, call_id)
    return key, created


def mark_transport_exported(
    path: Path,
    client: RedisClient,
    *,
    call_id: str,
    target: str,
    result_sha256: str,
) -> tuple[str, bool]:
    """Record a trusted local transport export after the Rust daemon has written it.

    The transport daemon is already inside the trusted server boundary, so this path
    does not use the old signed-effect envelope. The ledger remains lean: it stores
    only the call -> receipt-key fact while the short-lived receipt details stay in
    Redis.
    """
    if not isinstance(call_id, str) or not call_id:
        raise ExporterError("call_id is required")
    if not isinstance(target, str) or not target:
        raise ExporterError("export target is required")
    if (
        not isinstance(result_sha256, str)
        or len(result_sha256) != 64
        or any(ch not in "0123456789abcdef" for ch in result_sha256)
    ):
        raise ExporterError("result_sha256 must be a lowercase SHA-256 hex digest")

    key = f"export:{call_id}:receipt"
    client.hset(
        key,
        {
            "kind": "dropbox",
            "target": target,
            "result_sha256": result_sha256,
        },
    )
    client.expire(key, FORENSIC_TTL)
    created = record_export(path, call_id, key)
    retain_delivered(path, client, call_id)
    return key, created


def retain_delivered(path: Path, client: RedisClient, call_id: str) -> bool:
    """Bound forensic retention only after both completion and delivery facts."""
    if not call_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in call_id):
        raise ExporterError("Unsafe call identity")
    with closing(connect(path)) as db:
        has_direct_jobs = db.execute("SELECT 1 FROM sqlite_master WHERE name='ssh_jobs'").fetchone()
        if has_direct_jobs:
            direct_job = db.execute("SELECT state FROM ssh_jobs WHERE call_id=?", (call_id,)).fetchone()
            if direct_job and direct_job["state"] != "cleaned":
                return False
        if db.execute("SELECT 1 FROM responses JOIN exports USING(call_id) WHERE call_id=?",
                      (call_id,)).fetchone() is None:
            return False
    keys = call_keys(client, call_id)
    return bool(client.command("EVAL", """
        for _, key in ipairs(KEYS) do
            if string.sub(key, 1, 11) == 'claim:task:' and redis.call('HGET',key,'state') ~= 'done' then
                return 0
            end
        end
        for _, key in ipairs(KEYS) do
            if redis.call('TTL',key) == -1 then redis.call('EXPIRE',key,ARGV[1]) end
        end
        return 1
    """, len(keys), *keys, FORENSIC_TTL))


def reconcile_retention(path: Path, client: RedisClient) -> None:
    """Retry cleanup interrupted after the durable delivery acknowledgment."""
    ensure_schema(path)
    with closing(connect(path)) as db:
        calls = [str(row[0]) for row in db.execute("SELECT call_id FROM exports")]
    for call_id in calls:
        retain_delivered(path, client, call_id)


def call_keys(client: RedisClient, call_id: str) -> list[str]:
    if not call_id or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in call_id):
        raise ExporterError("Unsafe call identity")
    keys = [f"call:{call_id}:content", f"call:{call_id}:baggage",
            f"response:{call_id}:content", f"export:{call_id}:receipt", f"enqueue:{call_id}"]
    for pattern in (f"task:{call_id}:*", f"result:{call_id}:*", f"claim:task:{call_id}:*"):
        cursor = "0"
        while True:
            cursor, batch = client.command("SCAN", cursor, "MATCH", pattern, "COUNT", 100)
            keys.extend(batch)
            if str(cursor) == "0":
                break
    return keys


def protect_outstanding(path: Path, client: RedisClient) -> list[str]:
    """Clear legacy TTLs at startup; report already missing call payloads."""
    ensure_schema(path)
    with closing(connect(path)) as db:
        calls = {str(row[0]) for row in db.execute(
            "SELECT calls.call_id FROM calls LEFT JOIN exports USING(call_id) WHERE exports.call_id IS NULL")}
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='ssh_jobs'").fetchone():
            calls.update(str(row[0]) for row in db.execute(
                "SELECT call_id FROM ssh_jobs WHERE state != 'cleaned'"))
    missing = []
    for call_id in sorted(calls):
        keys = call_keys(client, call_id)
        for key in keys:
            client.persist(key)
        for key in (f"call:{call_id}:content", f"call:{call_id}:baggage"):
            if not client.hgetall(key):
                missing.append(key)
    return missing
