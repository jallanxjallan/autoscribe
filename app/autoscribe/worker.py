from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .redis_runtime import RedisClient

RESPONSE_TTL = 30 * 24 * 60 * 60


class WorkerError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtensionResult:
    task_key: str
    call_identity: str
    runtime_key: str
    source_identity: str
    executor: str
    entrypoint: str
    content: str


def load_registry(path: Path) -> dict[str, Path]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkerError(f"extension registry not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise WorkerError(f"invalid extension registry: {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise WorkerError("extension registry must be a JSON object")
    out: dict[str, Path] = {}
    for name, target in raw.items():
        if not isinstance(name, str) or not name or any(ch.isspace() for ch in name):
            raise WorkerError(f"invalid extension name: {name!r}")
        if not isinstance(target, str) or not target.startswith("/"):
            raise WorkerError(f"extension path must be absolute: {name}")
        out[name] = Path(target)
    return out


def run_extension(executable: Path, content: str, timeout: float = 30.0) -> str:
    if not executable.is_file():
        raise WorkerError(f"extension executable not found: {executable}")
    if not executable.stat().st_mode & 0o111:
        raise WorkerError(f"extension is not executable: {executable}")
    try:
        proc = subprocess.run(
            [str(executable)],
            input=content,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            close_fds=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise WorkerError(f"extension timed out: {executable.name}") from exc
    if proc.returncode != 0:
        err = proc.stderr.strip()
        suffix = f": {err}" if err else ""
        raise WorkerError(f"extension exited {proc.returncode}: {executable.name}{suffix}")
    return proc.stdout


def execute_task(client: RedisClient, task_key: str, registry: dict[str, Path], timeout: float = 30.0) -> ExtensionResult:
    task = client.hgetall(task_key)
    if not task:
        raise WorkerError(f"missing task: {task_key}")
    if task.get("state") != "ready":
        raise WorkerError(f"task is not ready: {task_key}")
    runtime_key = task.get("runtime_key", "")
    runtime = client.hgetall(runtime_key)
    if not runtime:
        raise WorkerError(f"missing runtime: {runtime_key}")
    executor = runtime.get("engine", "")
    entrypoint = runtime.get("model", "")
    if executor != "extension":
        raise WorkerError(f"unsupported worker executor: {executor}")
    executable = registry.get(entrypoint)
    if executable is None:
        raise WorkerError(f"unregistered extension: {entrypoint}")
    output = run_extension(executable, task.get("input", ""), timeout)
    return ExtensionResult(
        task_key=task_key,
        call_identity=task["call_identity"],
        runtime_key=runtime_key,
        source_identity=task["source_identity"],
        executor=executor,
        entrypoint=entrypoint,
        content=output,
    )


def persist_redis_response(client: RedisClient, response_identity: str, result: ExtensionResult) -> str:
    key = f"response:{response_identity}:record"
    client.hset(key, {
        "identity": response_identity,
        "call_identity": result.call_identity,
        "runtime_key": result.runtime_key,
        "task_key": result.task_key,
        "source_identity": result.source_identity,
        "executor": result.executor,
        "entrypoint": result.entrypoint,
        "content": result.content,
    })
    client.expire(key, RESPONSE_TTL)
    client.hset(result.task_key, {"state": "complete", "response_identity": response_identity})
    return key
