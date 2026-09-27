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

from autoscribe.executor import prepare_first_step
from autoscribe.ledger import append_event, has_event, load_call
from autoscribe.redis_runtime import ACTIVE_KEY, RedisClient

HOME = Path.home()
LEDGER_DB = Path(os.environ.get("AUTOSCRIBE_LEDGER_DB", str(HOME / "Data/ledger.sql")))
REDIS_HOST = os.environ.get("AUTOSCRIBE_REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("AUTOSCRIBE_REDIS_PORT", "6379"))
POLL_SECONDS = float(os.environ.get("AUTOSCRIBE_EXECUTOR_POLL_SECONDS", "2"))
MODE = os.environ.get("AUTOSCRIBE_EXECUTOR_MODE", "prepare-only")
running = True


def emit(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False, sort_keys=True), flush=True)


def call_identity_from_job(job_key: str) -> str:
    prefix, suffix = "job:", ":record"
    if not job_key.startswith(prefix) or not job_key.endswith(suffix):
        raise ValueError(f"invalid active job key: {job_key}")
    return job_key[len(prefix):-len(suffix)]


def stop(*_args) -> None:
    global running
    running = False


def process_active(client: RedisClient) -> None:
    for job_key in client.zrange(ACTIVE_KEY, 0, 31):
        call_identity = None
        try:
            call_identity = call_identity_from_job(job_key)
            if has_event(LEDGER_DB, call_identity, "executor_ready"):
                client.zrem(ACTIVE_KEY, job_key)
                continue
            if has_event(LEDGER_DB, call_identity, "executor_failed"):
                client.zrem(ACTIVE_KEY, job_key)
                continue
            call = load_call(LEDGER_DB, call_identity)
            ready = prepare_first_step(client, call_identity, call)
            detail = {
                "runtime_key": ready.runtime_key,
                "task_keys": ready.task_keys,
                "source_identities": ready.source_identities,
                "engine": ready.engine,
                "model": ready.model,
                "mode": MODE,
            }
            append_event(LEDGER_DB, call_identity, "executor_ready", detail)
            client.zrem(ACTIVE_KEY, job_key)
            emit("executor_ready", call_identity=call_identity, **detail)
        except Exception as exc:
            detail = {"job_key": job_key, "error": str(exc), "mode": MODE}
            if call_identity is not None:
                append_event(LEDGER_DB, call_identity, "executor_failed", detail)
            client.zrem(ACTIVE_KEY, job_key)
            emit("executor_failed", call_identity=call_identity, **detail)


def main() -> int:
    if MODE != "prepare-only":
        emit("fatal", error=f"unsupported executor mode: {MODE}")
        return 2
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    client = RedisClient(REDIS_HOST, REDIS_PORT)
    client.ping()
    emit("ready", mode=MODE, ledger_db=str(LEDGER_DB), redis=f"{REDIS_HOST}:{REDIS_PORT}")
    while running:
        process_active(client)
        time.sleep(POLL_SECONDS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
