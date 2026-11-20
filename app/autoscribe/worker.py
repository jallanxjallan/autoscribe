from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from biznet_common.llm import LLMError, respond
from biznet_common.redis import RedisClient
from .redis_state import FORENSIC_TTL, load_json

class WorkerError(RuntimeError):
    pass


@dataclass(frozen=True)
class TaskResult:
    task_key: str
    call_id: str
    ordinal: int
    engine_kind: str
    engine: str
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


def _step(content: dict, ordinal: int) -> dict:
    plan = content.get("plan") or {}
    steps = plan.get("steps") or []
    matches = [step for step in steps if int(step.get("position", -1)) == int(ordinal)]
    if len(matches) != 1:
        raise WorkerError(f"call plan has no unique step {ordinal}")
    return matches[0]


def _task_input(client: RedisClient, task: dict[str, str], content: dict) -> str:
    input_key = task.get("input_key")
    if input_key:
        record = client.hgetall(input_key)
        if not record or "content" not in record:
            raise WorkerError(f"missing step input: {input_key}")
        return str(record["content"])
    input_record = content.get("input") or {}
    value = input_record.get("content")
    if not isinstance(value, str):
        raise WorkerError(f"call content has no text input: {task.get('content_key', '')}")
    return value


def _instructions_text(step: dict) -> str:
    values = []
    for instruction in step.get("instructions") or []:
        body = instruction.get("body")
        if isinstance(body, str) and body.strip():
            values.append(body.strip())
    return "\n\n".join(values)


def _input_images(input_record: dict, content: str) -> list[tuple[str, str]]:
    mime_types = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                  "webp": "image/webp", "gif": "image/gif"}
    images = []
    for asset in input_record.get("assets", []):
        path = asset["path"]
        if f"]({path})" not in content:
            continue
        extension = Path(path).suffix.lower().lstrip(".")
        if extension not in mime_types:
            raise WorkerError(f"Unsupported model image format: {path}")
        try:
            data = bytes.fromhex(asset["content_hex"])
        except (KeyError, TypeError, ValueError):
            raise WorkerError(f"Invalid model image bytes: {path}") from None
        if not data or hashlib.sha256(data).hexdigest() != asset.get("sha256"):
            raise WorkerError(f"Model image checksum mismatch: {path}")
        encoded = base64.b64encode(data).decode("ascii")
        images.append((f"data:{mime_types[extension]};base64,{encoded}", "auto"))
    return images


def run_chatgpt(step: dict, content: str, timeout: float = 120.0, *, images=()) -> str:
    if step.get("engine_kind") != "llm" or step.get("engine") != "chatgpt":
        raise WorkerError("run_chatgpt requires llm/chatgpt step")
    try:
        result = respond("autoscribe-worker", step.get("model"), content,
                         instructions=_instructions_text(step), images=images, timeout=timeout,
                         parameters=step.get("args") or {})
    except LLMError as exc:
        raise WorkerError(str(exc)) from None
    logging.getLogger(__name__).info(
        "LLM response model=%s request_id=%s usage=%s", result.model, result.request_id, result.usage
    )
    return result.text


def execute_task(
    client: RedisClient,
    task_key: str,
    registry: dict[str, Path],
    script_timeout: float = 30.0,
    llm_timeout: float = 120.0,
) -> TaskResult:
    task = client.hgetall(task_key)
    if not task:
        raise WorkerError(f"missing task: {task_key}")
    call_id = task.get("call_id", "")
    content_key = task.get("content_key", "")
    if not call_id or not content_key:
        raise WorkerError(f"incomplete task: {task_key}")
    try:
        ordinal = int(task.get("ordinal", ""))
    except ValueError as exc:
        raise WorkerError(f"invalid task ordinal: {task_key}") from exc
    call_content = load_json(client, content_key)
    step = _step(call_content, ordinal)
    input_content = _task_input(client, task, call_content)
    engine_kind = str(step.get("engine_kind") or task.get("engine_kind") or "")
    engine = str(step.get("engine") or task.get("engine") or "")

    if engine_kind == "llm":
        if engine != "chatgpt":
            raise WorkerError(f"unsupported llm engine: {engine}")
        images = () if task.get("input_key") else _input_images(call_content.get("input") or {}, input_content)
        output = run_chatgpt(step, input_content, llm_timeout, images=images)
        entrypoint = str(step.get("model") or "")
    elif engine_kind == "script":
        entrypoint = str(step.get("script") or "")
        executable = registry.get(entrypoint)
        if executable is None:
            raise WorkerError(f"unregistered extension: {entrypoint}")
        output = run_extension(executable, input_content, script_timeout)
    elif engine_kind == "rag":
        entrypoint = str(step.get("rag_profile") or "")
        raise WorkerError(f"rag execution is not implemented: {entrypoint}")
    else:
        raise WorkerError(f"unsupported worker engine_kind: {engine_kind}")

    return TaskResult(
        task_key=task_key,
        call_id=call_id,
        ordinal=ordinal,
        engine_kind=engine_kind,
        engine=engine,
        entrypoint=entrypoint,
        content=output,
    )


def persist_step_result(client: RedisClient, result: TaskResult) -> str:
    key = f"result:{result.call_id}:{result.ordinal}:content"
    client.hset(
        key,
        {
            "content": result.content,
            "ordinal": result.ordinal,
            "engine_kind": result.engine_kind,
            "engine": result.engine,
            "entrypoint": result.entrypoint,
        },
    )
    client.expire(key, FORENSIC_TTL)
    return key


def persist_redis_response(client: RedisClient, result: TaskResult) -> str:
    key = f"response:{result.call_id}:content"
    client.hset(
        key,
        {
            "schema": "autoscribe.response.v1",
            "call_id": result.call_id,
            "content": result.content,
            "ordinal": result.ordinal,
            "engine_kind": result.engine_kind,
            "engine": result.engine,
            "entrypoint": result.entrypoint,
        },
    )
    client.expire(key, FORENSIC_TTL)
    return key
