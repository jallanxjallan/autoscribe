#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from autoscribe.ledger import append_event, record_response
from autoscribe.redis_runtime import READY_KEY, RedisClient
from autoscribe.worker import execute_task, load_registry, persist_redis_response

HOME = Path.home()
LEDGER_DB = Path(os.environ.get("AUTOSCRIBE_LEDGER_DB", str(HOME / "Data/ledger.sql")))
REGISTRY = Path(os.environ.get("AUTOSCRIBE_EXTENSION_REGISTRY", "/opt/autoscribe/extensions/registry.json"))
REDIS_HOST = os.environ.get("AUTOSCRIBE_REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("AUTOSCRIBE_REDIS_PORT", "6379"))
POLL_SECONDS = float(os.environ.get("AUTOSCRIBE_WORKER_POLL_SECONDS", "1"))
TIMEOUT_SECONDS = float(os.environ.get("AUTOSCRIBE_EXTENSION_TIMEOUT_SECONDS", "30"))
running = True


def emit(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False, sort_keys=True), flush=True)


def stop(*_args) -> None:
    global running
    running = False


def process_ready(client: RedisClient, registry: dict[str, Path]) -> None:
    for task_key in client.zrange(READY_KEY, 0, 31):
        # One local worker in this alpha. Remove before execution so a deterministic
        # failure is terminal instead of becoming a tight retry loop.
        client.zrem(READY_KEY, task_key)
        call_identity = None
        try:
            task = client.hgetall(task_key)
            call_identity = task.get("call_identity") if task else None
            result = execute_task(client, task_key, registry, TIMEOUT_SECONDS)
            response_identity, created = record_response(
                LEDGER_DB,
                call_identity=result.call_identity,
                runtime_key=result.runtime_key,
                task_key=result.task_key,
                source_identity=result.source_identity,
                executor=result.executor,
                entrypoint=result.entrypoint,
                content=result.content,
            )
            response_key = persist_redis_response(client, response_identity, result)
            detail = {
                "task_key": task_key,
                "response_identity": response_identity,
                "response_key": response_key,
                "source_identity": result.source_identity,
                "executor": result.executor,
                "entrypoint": result.entrypoint,
                "created": created,
            }
            append_event(LEDGER_DB, result.call_identity, "worker_completed", detail)
            emit("worker_completed", call_identity=result.call_identity, **detail)
        except Exception as exc:
            detail = {"task_key": task_key, "error": str(exc)}
            if call_identity:
                append_event(LEDGER_DB, call_identity, "worker_failed", detail)
            client.hset(task_key, {"state": "failed", "error": str(exc)})
            emit("worker_failed", call_identity=call_identity, **detail)


def main() -> int:
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    registry = load_registry(REGISTRY)
    client = RedisClient(REDIS_HOST, REDIS_PORT)
    client.ping()
    emit("ready", registry=str(REGISTRY), extensions=sorted(registry), redis=f"{REDIS_HOST}:{REDIS_PORT}")
    while running:
        process_ready(client, registry)
        time.sleep(POLL_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
