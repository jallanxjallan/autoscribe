from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Iterator

from .ledger import pending_exports, record_export
from .redis_runtime import FORENSIC_TTL, RedisClient, load_json


class EffectsError(RuntimeError):
    pass


def pending_count(path: Path) -> int:
    return len(pending_exports(path))


def build_pending_record(client: RedisClient, *, call_id: str, baggage_key: str) -> dict:
    baggage = load_json(client, baggage_key)
    if not isinstance(baggage, dict):
        raise EffectsError(f"invalid baggage record: {baggage_key}")
    return {
        "schema": "autoscribe.effect-pending.v1",
        "submission_id": load_json(client, f"call:{call_id}:content")["submission_id"],
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
                "schema": "autoscribe.effect-pending-error.v1",
                "call_id": call_id,
                "error": str(exc),
            }
        yield json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def poke_responses(path: Path, socket_path: Path) -> int:
    """Notify the signed-output coordinator that unexported rows exist."""
    count = pending_count(path)
    if count == 0:
        return 0
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    try:
        sock.sendto(str(count).encode("ascii"), str(socket_path))
    except OSError as exc:
        raise EffectsError(f"could not notify Responses at {socket_path}: {exc}") from exc
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
    """Persist a authenticated repository effect receipt and corresponding SQLite fact."""
    if not isinstance(receipt, dict):
        raise EffectsError("export receipt is not an object")
    if receipt.get("schema") != "autoscribe.receipt.v2":
        raise EffectsError(f"invalid export receipt schema: {receipt.get('schema')!r}")

    fields = {}
    for field in ("effect_key", "kind", "target", "result"):
        value = receipt.get(field)
        if not isinstance(value, str) or not value:
            raise EffectsError(f"export receipt missing {field}")
        fields[field] = value

    fields.update(submission_id=receipt['submission_id'],call_id=receipt['call_id'],baggage=json.dumps(receipt['baggage'],ensure_ascii=False))
    if receipt['call_id']!=call_id:raise EffectsError('Receipt call identity mismatch')
    if receipt['submission_id']!=load_json(client,f"call:{call_id}:content")['submission_id']:
        raise EffectsError('Receipt submission identity mismatch')
    original=load_json(client,f"call:{call_id}:baggage")
    if receipt['baggage']!=original:raise EffectsError('Receipt baggage mismatch')
    key = f"export:{call_id}:receipt"
    client.hset(key, fields)
    client.expire(key, FORENSIC_TTL)
    created = record_export(path, call_id, key)
    return key, created
