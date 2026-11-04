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

from autoscribe.claims import Claim
from autoscribe.executor import next_step_ordinal, prepare_step
from autoscribe.ledger import record_response
from autoscribe.redis_runtime import FORENSIC_TTL, WORKER_QUEUE_KEY, RedisClient, load_json
from autoscribe.worker import TaskResult, TerminalAdapterError, execute_task, load_registry, persist_redis_response

HOME = Path.home()
LEDGER_DB = Path(os.environ.get("AUTOSCRIBE_LEDGER_DB", str(HOME / "Data/ledger.sql")))
REGISTRY = Path(os.environ.get("AUTOSCRIBE_EXTENSION_REGISTRY", "/opt/autoscribe/extensions/registry.json"))
REDIS_HOST = os.environ.get("AUTOSCRIBE_REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("AUTOSCRIBE_REDIS_PORT", "6379"))
POLL_SECONDS = float(os.environ.get("AUTOSCRIBE_WORKER_POLL_SECONDS", "1"))
SCRIPT_TIMEOUT = float(os.environ.get("AUTOSCRIBE_EXTENSION_TIMEOUT_SECONDS", "30"))
LLM_TIMEOUT = float(os.environ.get("AUTOSCRIBE_LLM_TIMEOUT_SECONDS", "120"))
CLAIM_LEASE = int(os.environ.get("AUTOSCRIBE_WORKER_CLAIM_SECONDS", str(int(max(SCRIPT_TIMEOUT, LLM_TIMEOUT)) + 30)))
running = True


def emit(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False, sort_keys=True), flush=True)


def stop(*_args) -> None:
    global running
    running = False


def finish_result(client: RedisClient, task_key: str, task: dict, call_id: str) -> None:
    ordinal = int(task["ordinal"])
    result_key = f"result:{call_id}:{ordinal}:content"
    result = client.hgetall(result_key)
    if "content" not in result:
        raise RuntimeError(f"Committed step result unavailable: {result_key}")
    content = load_json(client, task["content_key"])
    next_ordinal = next_step_ordinal(content, ordinal)
    if next_ordinal is not None and result.get("terminal_failure") != "1":
        prepare_step(client, call_id, task["content_key"], next_ordinal, input_key=result_key)
        emit("worker_step_completed", call_id=call_id, task_key=task_key, ordinal=ordinal)
        return
    response = TaskResult(task_key, call_id, ordinal, result["engine_kind"],
                          result["engine"], result["entrypoint"], result["content"])
    response_key = persist_redis_response(client, response)
    record_response(LEDGER_DB, call_id, response_key)
    emit("worker_completed", call_id=call_id, task_key=task_key, response_key=response_key)


def process_task(client: RedisClient, registry: dict[str, Path], task_key: str) -> None:
    claim = Claim(client, task_key)
    state = claim.acquire(CLAIM_LEASE)
    if not state:
        return
    if state == "uncertain":
        emit("worker_uncertain", task_key=task_key)
        return
    task = client.hgetall(task_key)
    call_id = task["call_id"]
    if state == "claimed":
        if not claim.transition("claimed", "running"):
            return
        failure = ""
        try:
            result = execute_task(client, task_key, registry, script_timeout=SCRIPT_TIMEOUT,
                                  llm_timeout=LLM_TIMEOUT)
        except TerminalAdapterError as exc:
            failure = str(exc)
            result = TaskResult(task_key, call_id, int(task["ordinal"]), task["engine_kind"],
                                task["engine"], task["entrypoint"], "Unreadable")
        except Exception as exc:
            if claim.transition("running", "uncertain", error=str(exc)):
                key = f"diagnostic:{call_id}:worker"
                client.hset(key, {"task_key": task_key, "error": str(exc)})
                client.expire(key, FORENSIC_TTL)
                emit("worker_failed", call_id=call_id, task_key=task_key, diagnostic_key=key, error=str(exc))
            return
        if not claim.transition(
            "running", "result", error=failure,
            result_key=f"result:{call_id}:{result.ordinal}:content", ttl=FORENSIC_TTL,
            fields={"content": result.content, "ordinal": result.ordinal, "engine_kind": result.engine_kind,
                    "engine": result.engine, "entrypoint": result.entrypoint, "terminal_failure": int(bool(failure))},
        ):
            return
    finish_result(client, task_key, task, call_id)
    claim.transition("result", "done")


def process_ready(client: RedisClient, registry: dict[str, Path]) -> None:
    for task_key in client.zrange(WORKER_QUEUE_KEY, 0, -1):
        if not running:
            break
        try:
            process_task(client, registry, task_key)
        except Exception as exc:
            emit("worker_recovery_deferred", task_key=task_key, error=str(exc))


def main() -> int:
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    registry = load_registry(REGISTRY)
    client = RedisClient(REDIS_HOST, REDIS_PORT)
    client.ping()
    emit(
        "ready",
        registry=str(REGISTRY),
        extensions=sorted(registry),
        redis=f"{REDIS_HOST}:{REDIS_PORT}",
        llm_timeout=LLM_TIMEOUT,
    )
    while running:
        process_ready(client, registry)
        time.sleep(POLL_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
