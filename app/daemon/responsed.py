#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from autoscribe.exporter import mark_exported
from autoscribe.redis_runtime import RedisClient

HOME = Path.home()

ASC = Path(os.environ.get(
    "AUTOSCRIBE_ASC",
    str(HOME / ".local/bin/asc"),
))
LEDGER_DB = Path(os.environ.get(
    "AUTOSCRIBE_LEDGER_DB",
    str(HOME / "Data/ledger.sql"),
))
SOCKET_PATH = Path(os.environ.get(
    "AUTOSCRIBE_RESPONSE_SOCKET",
    str(HOME / ".local/run/autoscribe/response.sock"),
))

POLICY = Path(os.environ.get(
    "AUTOSCRIBE_SERVICES_POLICY",
    "/etc/autoscribe/services.toml",
))
SERVICES = Path(os.environ.get(
    "AUTOSCRIBE_SERVICES",
    "/opt/autoscribe/services/current/bin",
))

SRV_OUTPUT = SERVICES / "srv-output"
SRV_WRITEBACK = SERVICES / "srv-writeback"
SRV_EXPORT = SERVICES / "srv-export"

REDIS_HOST = os.environ.get("AUTOSCRIBE_REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("AUTOSCRIBE_REDIS_PORT", "6379"))

sock: socket.socket | None = None
running = True


class ResponsesError(RuntimeError):
    pass


def emit(event: str, **fields) -> None:
    print(
        json.dumps(
            {"event": event, **fields},
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )


def run_command(
    argv: list[str],
    *,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        input=input_text,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def run_asc(*args: str) -> subprocess.CompletedProcess[str]:
    return run_command([str(ASC), *args])


def parse_one_ndjson(text: str, label: str) -> dict:
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ResponsesError(
            f"{label} returned {len(lines)} records; expected exactly one"
        )
    try:
        value = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise ResponsesError(f"{label} returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ResponsesError(f"{label} response is not an object")
    return value


def load_pending() -> list[dict]:
    cp = run_asc("export", "pending")
    if cp.returncode != 0:
        raise ResponsesError(
            cp.stderr.strip() or "asc export pending failed"
        )

    records: list[dict] = []
    for number, raw in enumerate(cp.stdout.splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ResponsesError(
                f"invalid pending NDJSON line {number}: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise ResponsesError(
                f"pending NDJSON line {number} is not an object"
            )
        records.append(value)

    records.sort(key=lambda record: str(record.get("call_id", "")))
    return records


def route_info(record: dict) -> tuple[str, str, tuple[str, ...]]:
    if record.get("schema") != "autoscribe.export-pending.v1":
        raise ResponsesError(
            record.get("error")
            or f"unsupported pending schema: {record.get('schema')!r}"
        )

    call_id = record.get("call_id")
    baggage = record.get("baggage")

    if not isinstance(call_id, str) or not call_id:
        raise ResponsesError("pending export has no call_id")
    if not isinstance(baggage, dict):
        raise ResponsesError(f"pending export {call_id} has no baggage")

    envelope = baggage.get("autoscribe_return")
    if not isinstance(envelope, dict):
        raise ResponsesError(
            f"pending export {call_id} has no autoscribe_return"
        )

    route = envelope.get("route")
    if not isinstance(route, dict):
        raise ResponsesError(
            f"pending export {call_id} has no return route"
        )

    kind = route.get("kind")

    if kind == "repo":
        repo = route.get("repo")
        path = route.get("path")
        if not isinstance(repo, str) or not repo:
            raise ResponsesError(f"{call_id} repo route missing repo")
        if not isinstance(path, str) or not path:
            raise ResponsesError(f"{call_id} repo route missing path")
        return call_id, kind, ("repo", repo, path)

    if kind == "dropbox":
        batch = route.get("batch")
        path = route.get("path")
        if not isinstance(batch, str) or not batch:
            raise ResponsesError(f"{call_id} Dropbox route missing batch")
        if not isinstance(path, str) or not path:
            raise ResponsesError(f"{call_id} Dropbox route missing path")
        return call_id, kind, ("dropbox", batch, path)

    raise ResponsesError(
        f"unsupported return route for {call_id}: {kind!r}"
    )


def process_record(redis: RedisClient, record: dict) -> None:
    call_id, hinted_kind, _route_key = route_info(record)

    response_cp = run_asc("response", call_id)
    if response_cp.returncode != 0:
        raise ResponsesError(
            response_cp.stderr.strip()
            or f"asc response failed for {call_id}"
        )

    output_cp = run_command(
        [str(SRV_OUTPUT), "--policy", str(POLICY)],
        input_text=response_cp.stdout,
    )
    if output_cp.returncode != 0:
        raise ResponsesError(
            output_cp.stderr.strip()
            or f"srv-output failed for {call_id}"
        )

    effect = parse_one_ndjson(output_cp.stdout, "srv-output")
    effect_body = effect.get("effect")
    if not isinstance(effect_body, dict):
        raise ResponsesError(
            f"srv-output effect for {call_id} has no effect object"
        )

    trusted_kind = effect_body.get("kind")
    if trusted_kind != hinted_kind:
        raise ResponsesError(
            f"route kind mismatch for {call_id}: "
            f"pending={hinted_kind!r}, trusted={trusted_kind!r}"
        )

    if trusted_kind == "repo":
        handler = SRV_WRITEBACK
    elif trusted_kind == "dropbox":
        handler = SRV_EXPORT
    else:
        raise ResponsesError(
            f"unsupported trusted effect kind for {call_id}: "
            f"{trusted_kind!r}"
        )

    handler_cp = run_command(
        [str(handler), "--policy", str(POLICY)],
        input_text=output_cp.stdout,
    )
    if handler_cp.returncode != 0:
        raise ResponsesError(
            handler_cp.stderr.strip()
            or f"{handler.name} failed for {call_id}"
        )

    receipt = parse_one_ndjson(handler_cp.stdout, handler.name)

    receipt_key, created = mark_exported(
        LEDGER_DB,
        redis,
        call_id=call_id,
        receipt=receipt,
    )

    emit(
        "response_exported",
        call_id=call_id,
        kind=receipt.get("kind"),
        target=receipt.get("target"),
        result=receipt.get("result"),
        effect_key=receipt.get("effect_key"),
        receipt_key=receipt_key,
        created=created,
    )


def process_pending() -> None:
    records = load_pending()
    if not records:
        emit("responses_idle", pending=0)
        return

    redis = RedisClient(REDIS_HOST, REDIS_PORT)
    redis.ping()

    blocked: set[tuple[str, ...]] = set()

    for record in records:
        try:
            call_id, _kind, route_key = route_info(record)
        except Exception as exc:
            emit(
                "response_failed",
                call_id=record.get("call_id"),
                stage="route",
                error=str(exc),
            )
            continue

        if route_key in blocked:
            emit(
                "response_deferred",
                call_id=call_id,
                stage="ordering",
                reason="earlier response for same destination failed",
            )
            continue

        try:
            process_record(redis, record)
        except Exception as exc:
            blocked.add(route_key)
            emit(
                "response_failed",
                call_id=call_id,
                stage="export",
                error=str(exc),
            )


def stop(*_args) -> None:
    global running, sock
    running = False
    if sock is not None:
        try:
            sock.close()
        except OSError:
            pass


def cleanup() -> None:
    try:
        SOCKET_PATH.unlink()
    except FileNotFoundError:
        pass


def main() -> int:
    global sock

    if sys.argv[1:] == ["--once"]:
        try:
            process_pending()
        except Exception as exc:
            emit("responses_failed", stage="once", error=str(exc))
            return 1
        return 0

    if sys.argv[1:]:
        print("usage: responsed.py [--once]", file=sys.stderr)
        return 2

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    cleanup()

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind(str(SOCKET_PATH))
    os.chmod(SOCKET_PATH, 0o600)

    emit(
        "ready",
        socket=str(SOCKET_PATH),
        ledger_db=str(LEDGER_DB),
        redis=f"{REDIS_HOST}:{REDIS_PORT}",
        asc=str(ASC),
        services=str(SERVICES),
    )

    try:
        process_pending()
    except Exception as exc:
        emit("responses_failed", stage="startup", error=str(exc))

    try:
        while running:
            try:
                data = sock.recv(128)
            except (InterruptedError, OSError):
                if running:
                    continue
                break

            try:
                notice = int(data.decode("ascii").strip())
            except Exception:
                emit(
                    "notice_rejected",
                    raw=data.decode("utf-8", "replace"),
                )
                continue

            emit("notice", pending=notice)

            try:
                process_pending()
            except Exception as exc:
                emit("responses_failed", stage="query", error=str(exc))
    finally:
        cleanup()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
