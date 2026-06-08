"""Atomic runtime step worker.

Queue member:
    runtime:<identity>:step.<n>

Execution flow:
    claim step key
    load runtime step record
    load content at position n
    resolve step.definition.engine through registry loader
    call engine make_call(...)
    write content at position n + 1
    update content-index
    enqueue step n + 1 if it exists

Failure rule:
    if execution fails after claim, requeue the same step key with its
    original score, then re-raise the exception.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import redis

from asc.core.timestamp import timestamp
from asc.models.runtime.result import StepResultRecord
from asc.registries.extensions import load_engine_call
from asc.state.runtime_step_queue import claim_next, enqueue_step
from asc.state.scrivener_queue import enqueue as enqueue_result


@dataclass(frozen=True, slots=True)
class AtomicStepResult:
    processed: int
    step_key: str | None = None
    output_key: str | None = None
    next_step_key: str | None = None


class StepProbeWorker:
    def __init__(self) -> None:
        self.redis = redis.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )

    def run(self) -> int:
        result = self.run_once()

        if result.processed == 0:
            print("[run] queue empty")
            return 0

        print(f"[run] executed={result.step_key}")
        print(f"[run] wrote={result.output_key}")

        if result.next_step_key:
            print(f"[run] enqueued_next={result.next_step_key}")
        else:
            print("[run] terminal_step=true")

        return result.processed

    def run_once(self) -> AtomicStepResult:
        claimed = claim_next()
        if claimed is None:
            return AtomicStepResult(processed=0)

        try:
            return self._execute_step_key(claimed.step_key)
        except Exception:
            enqueue_step(claimed.step_key, score=claimed.score)
            raise

    def _execute_step_key(self, step_key: str) -> AtomicStepResult:
        step_record = self._load_json_string(step_key)

        identity = self._require_string(step_record, "identity")
        step_number = self._require_int(step_record, "step_number")
        definition = self._require_dict(step_record, "definition")

        engine_name = self._require_string(definition, "engine")
        args = self._require_dict(definition, "args")

        content_index_key = self._runtime_key(identity, "content-index")
        step_index_key = self._runtime_key(identity, "step-index")

        input_key = self.redis.hget(content_index_key, str(step_number))
        if not input_key:
            raise RuntimeError(
                f"missing input content index: {content_index_key}[{step_number}]"
            )

        input_record = self._load_json_string(input_key)
        input_content = self._require_string(input_record, "content")

        make_call = load_engine_call(engine_name)
        call = make_call(args=args)

        if not callable(call):
            raise TypeError(
                f"engine {engine_name!r} make_call(...) did not return a callable"
            )

        started_at = timestamp()
        output_content = call(input_content)
        completed_at = timestamp()

        if not isinstance(output_content, str):
            raise TypeError(
                f"engine {engine_name!r} returned {type(output_content).__name__}; "
                "expected str"
            )

        output_position = step_number + 1
        output_key = self._runtime_key(identity, f"content.{output_position}")

        output_record = {
            "identity": identity,
            "position": output_position,
            "origin": "step",
            "produced_by_step": step_number,
            "content": output_content,
        }

        self.redis.set(output_key, json.dumps(output_record, ensure_ascii=False))
        self.redis.hset(content_index_key, str(output_position), output_key)

        result_record = StepResultRecord(
            call_identity=identity,
            step_number=step_number,
            raw_json={
                "engine": engine_name,
                "args": args,
            },
            content=output_content,
            fail_message=None,
            started_at=started_at,
            completed_at=completed_at,
            input_key=input_key,
            output_key=output_key,
            handler=self._handler_from_args(args),
            engine=engine_name,
            prompt=input_content,
            input_content=input_content,
        )
        result_record.save()
        enqueue_result(result_record.identity)

        next_step_key = self.redis.hget(step_index_key, str(output_position))
        if next_step_key:
            enqueue_step(next_step_key)

        return AtomicStepResult(
            processed=1,
            step_key=step_key,
            output_key=output_key,
            next_step_key=next_step_key,
        )

    def _load_json_string(self, key: str) -> dict[str, Any]:
        redis_type = self.redis.type(key)
        if redis_type != "string":
            raise TypeError(f"{key} must be a Redis string; got {redis_type}")

        raw = self.redis.get(key)
        if raw is None:
            raise KeyError(f"missing Redis key: {key}")

        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise TypeError(f"{key} must contain a JSON object")

        return parsed

    def _runtime_key(self, identity: str, suffix: str) -> str:
        return f"runtime:{identity}:{suffix}"

    def _handler_from_args(self, args: dict[str, Any]) -> str | None:
        for key in ("handler", "script", "label"):
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _require_string(self, record: dict[str, Any], field: str) -> str:
        value = record.get(field)
        if not isinstance(value, str) or not value.strip():
            raise TypeError(f"{field} must be a non-empty string")
        return value

    def _require_int(self, record: dict[str, Any], field: str) -> int:
        value = record.get(field)
        if not isinstance(value, int):
            raise TypeError(f"{field} must be an int")
        return value

    def _require_dict(self, record: dict[str, Any], field: str) -> dict[str, Any]:
        value = record.get(field)
        if not isinstance(value, dict):
            raise TypeError(f"{field} must be an object")
        return value
