"""Atomic runtime step worker.

Queue member:
    runtime:<identity>:call-state or equivalent full RuntimeCallState key

Contract:
    - Worker claims one full call_state key from the worker queue.
    - CallState exposes mutable execution keys only: step_key and response_key.
    - The immutable CallRecord referenced by call_state.call_key owns prompt_key.
    - Worker loads those records, executes one already-materialized step, writes
      only the response artifact, annotates CallState, and returns the same
      call_state key to the single orchestrator queue.
    - Worker does not parse plan master records.
    - Worker does not synthesize runtime keys.
    - Worker does not read content/step indexes.
    - Worker does not enqueue next steps.
    - Worker does not write ledger/result records.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import redis

from asc.core.timestamp import timestamp
from asc.models.runtime.call import CallRecord
from asc.models.runtime.call_state import RuntimeCallState
from asc.models.runtime.step import RuntimeStepRecord
from asc.registries.extensions import load_engine_call
from asc.state import orchestrator_queue, worker_queue


@dataclass(frozen=True, slots=True)
class AtomicStepResult:
    processed: int
    call_state_key: str | None = None
    step_key: str | None = None
    prompt_key: str | None = None
    response_key: str | None = None
    status: str | None = None


class StepProbeWorker:
    def __init__(self) -> None:
        self.redis = redis.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )

    def run(self) -> int:
        result = self.run_once()

        if result.processed == 0:
            print("[worker] queue empty")
            return 0

        print(f"[worker] call_state={result.call_state_key}")
        print(f"[worker] step={result.step_key}")
        print(f"[worker] read={result.prompt_key}")
        print(f"[worker] wrote={result.response_key}")
        print(f"[worker] status={result.status}")
        print(f"[worker] returned_to_orchestrator={result.call_state_key}")
        return result.processed

    def run_once(self) -> AtomicStepResult:
        claimed = worker_queue.claim_next()
        if claimed is None:
            return AtomicStepResult(processed=0)

        call_state_key = self._claimed_key(claimed)

        try:
            return self._execute_call_state(call_state_key)
        except Exception as exc:
            # Retry policy belongs in asc.orchestrator.policy.
            # Worker reports failures; orchestrator decides whether to retry,
            # delay, abandon, or escalate. Import/apply that policy here only if
            # we later formalize worker-side retry authorization.
            self._report_failure(call_state_key, exc)
            raise

    def _execute_call_state(self, call_state_key: str) -> AtomicStepResult:
        call_state = RuntimeCallState.load(call_state_key)

        call_key = self._required_attr(call_state, "call_key")
        call_record = CallRecord.load(call_key)

        step_key = self._required_attr(call_state, "step_key")
        prompt_key = self._required_attr(call_record, "prompt_key")
        response_key = self._required_attr(call_state, "response_key")

        step_record = RuntimeStepRecord.load(step_key)
        definition = self._required_attr(step_record, "definition")
        if not isinstance(definition, dict):
            raise TypeError("step.definition must be an object")

        engine_name = self._required_mapping_string(definition, "engine")
        args = self._required_mapping_dict(definition, "args")

        input_content = self._load_content(prompt_key)

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

        self._write_response_artifact(
            response_key=response_key,
            content=output_content,
            call_state=call_state,
            step_key=step_key,
            prompt_key=prompt_key,
            engine=engine_name,
            args=args,
            started_at=started_at,
            completed_at=completed_at,
        )

        self._mark_success(
            call_state,
            step_key=step_key,
            prompt_key=prompt_key,
            response_key=response_key,
            engine=engine_name,
            started_at=started_at,
            completed_at=completed_at,
        )
        call_state.save()
        orchestrator_queue.enqueue(call_state_key)

        return AtomicStepResult(
            processed=1,
            call_state_key=call_state_key,
            step_key=step_key,
            prompt_key=prompt_key,
            response_key=response_key,
            status="success",
        )

    def _report_failure(self, call_state_key: str, exc: BaseException) -> None:
        try:
            call_state = RuntimeCallState.load(call_state_key)
            setattr(call_state, "status", "failed")
            setattr(call_state, "failure_message", str(exc))
            setattr(call_state, "failed_at", timestamp())
            call_state.save()
        finally:
            orchestrator_queue.enqueue(call_state_key)

    def _load_content(self, key: str) -> str:
        record = self._load_json_string(key)
        value = record.get("content", record.get("record_content"))
        if not isinstance(value, str):
            raise TypeError(f"{key} must contain string content")
        return value

    def _write_response_artifact(
        self,
        *,
        response_key: str,
        content: str,
        call_state: RuntimeCallState,
        step_key: str,
        prompt_key: str,
        engine: str,
        args: dict[str, Any],
        started_at: float,
        completed_at: float,
    ) -> None:
        record: dict[str, Any] = {
            "identity": self._optional_attr(call_state, "call_identity"),
            "origin": "worker",
            "content": content,
            "step_key": step_key,
            "prompt_key": prompt_key,
            "response_key": response_key,
            "engine": engine,
            "args": args,
            "started_at": started_at,
            "completed_at": completed_at,
        }
        record = {key: value for key, value in record.items() if value is not None}
        self.redis.set(response_key, json.dumps(record, ensure_ascii=False))

    def _mark_success(
        self,
        call_state: RuntimeCallState,
        *,
        step_key: str,
        prompt_key: str,
        response_key: str,
        engine: str,
        started_at: float,
        completed_at: float,
    ) -> None:
        setattr(call_state, "status", "success")
        setattr(call_state, "worker_status", "success")
        setattr(call_state, "completed_step_key", step_key)
        # prompt_key belongs to CallRecord, not mutable CallState.
        setattr(call_state, "completed_response_key", response_key)
        setattr(call_state, "completed_engine", engine)
        setattr(call_state, "started_at", started_at)
        setattr(call_state, "completed_at", completed_at)
        setattr(call_state, "failure_message", None)

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

    def _claimed_key(self, claimed: Any) -> str:
        value = getattr(claimed, "call_state_key", None)
        if value is None:
            value = getattr(claimed, "identity", None)
        if value is None:
            value = getattr(claimed, "step_key", None)
        if value is None:
            value = claimed
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if not isinstance(value, str) or not value.strip():
            raise TypeError("worker queue claim must provide a full call_state key")
        return value.strip()

    def _required_attr(self, obj: Any, name: str) -> Any:
        if not hasattr(obj, name):
            raise TypeError(f"{type(obj).__name__} missing required field: {name}")
        value = getattr(obj, name)
        if value is None:
            raise TypeError(f"{type(obj).__name__}.{name} must be non-empty")
        if isinstance(value, str) and not value.strip():
            raise TypeError(f"{type(obj).__name__}.{name} must be non-empty")
        return value

    def _optional_attr(self, obj: Any, name: str) -> Any:
        return getattr(obj, name, None)

    def _required_mapping_string(self, mapping: dict[str, Any], key: str) -> str:
        value = mapping.get(key)
        if not isinstance(value, str) or not value.strip():
            raise TypeError(f"step.definition.{key} must be a non-empty string")
        return value.strip()

    def _required_mapping_dict(self, mapping: dict[str, Any], key: str) -> dict[str, Any]:
        value = mapping.get(key)
        if not isinstance(value, dict):
            raise TypeError(f"step.definition.{key} must be an object")
        return value
