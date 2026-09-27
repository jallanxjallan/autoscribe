from __future__ import annotations

import json
from dataclasses import dataclass
from .redis_runtime import READY_KEY, RedisClient

TASK_TTL = 24 * 60 * 60

class ExecutorError(RuntimeError): pass

@dataclass(frozen=True)
class PreparedExecution:
    call_identity: str
    runtime_key: str
    task_keys: list[str]
    source_identities: list[str]
    engine: str
    model: str

def _require_hash(client: RedisClient, key: str) -> dict[str, str]:
    value = client.hgetall(key)
    if not value: raise ExecutorError(f"missing Redis hash: {key}")
    return value

def prepare_first_step(client: RedisClient, call_identity: str, call: dict) -> PreparedExecution:
    steps = call.get("plan", {}).get("steps") or []
    if not steps: raise ExecutorError("call plan has no steps")
    first = min(steps, key=lambda step: int(step["position"])); ordinal = int(first["position"])
    runtime_key = f"runtime:{call_identity}:{ordinal}"; runtime = _require_hash(client, runtime_key)
    if runtime.get("plan_identity") != call["plan"]["id"]: raise ExecutorError("runtime plan identity does not match ledger call")
    instruction_keys = json.loads(runtime.get("instruction_keys", "[]"))
    if not isinstance(instruction_keys, list) or not instruction_keys: raise ExecutorError("runtime has no instruction keys")
    for key in instruction_keys:
        record = _require_hash(client, str(key))
        if record.get("call_identity") != call_identity: raise ExecutorError(f"instruction belongs to another call: {key}")
    sources = call.get("sources") or []
    if not sources: raise ExecutorError("canonical call has no ingested sources")
    task_keys=[]; source_identities=[]
    for index, item in enumerate(sources, start=1):
        task_key=f"task:{call_identity}:{ordinal}:{index}"
        client.hset(task_key, {
            "call_identity": call_identity, "runtime_key": runtime_key, "ordinal": ordinal,
            "source_identity": item["identity"], "source_path": item["path"], "source_blob": item["blob"],
            "directive": item.get("directive") or "", "input": item["content"],
            "instruction_keys": json.dumps(instruction_keys, separators=(",", ":")),
            "engine": runtime["engine"], "model": runtime["model"], "state": "ready",
        })
        client.expire(task_key, TASK_TTL); client.zadd(READY_KEY, 0, task_key)
        task_keys.append(task_key); source_identities.append(str(item["identity"]))
    return PreparedExecution(call_identity, runtime_key, task_keys, source_identities, runtime["engine"], runtime["model"])
