from __future__ import annotations

import json
import socket
from dataclasses import dataclass

CALL_TTL = 30 * 24 * 60 * 60
INSTRUCTION_TTL = 3 * 24 * 60 * 60
RUNTIME_TTL = 24 * 60 * 60
ACTIVE_KEY = "state:active:index"
READY_KEY = "state:ready:index"


class RedisError(RuntimeError):
    pass


class RedisClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 6379, timeout: float = 2.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    @staticmethod
    def _encode(parts: tuple[object, ...]) -> bytes:
        encoded = [f"*{len(parts)}\r\n".encode()]
        for part in parts:
            data = str(part).encode("utf-8")
            encoded.append(f"${len(data)}\r\n".encode())
            encoded.append(data + b"\r\n")
        return b"".join(encoded)

    @staticmethod
    def _readline(f) -> bytes:
        line = f.readline()
        if not line.endswith(b"\r\n"):
            raise RedisError("short Redis reply")
        return line[:-2]

    @classmethod
    def _read_reply(cls, f):
        prefix = f.read(1)
        if prefix == b"+":
            return cls._readline(f).decode("utf-8")
        if prefix == b":":
            return int(cls._readline(f))
        if prefix == b"$":
            length = int(cls._readline(f))
            if length == -1:
                return None
            data = f.read(length)
            if f.read(2) != b"\r\n":
                raise RedisError("malformed bulk reply")
            return data.decode("utf-8")
        if prefix == b"*":
            length = int(cls._readline(f))
            if length == -1:
                return None
            return [cls._read_reply(f) for _ in range(length)]
        if prefix == b"-":
            raise RedisError(cls._readline(f).decode("utf-8"))
        raise RedisError(f"unsupported Redis reply prefix: {prefix!r}")

    def command(self, *parts: object):
        with socket.create_connection((self.host, self.port), self.timeout) as s:
            s.sendall(self._encode(parts))
            f = s.makefile("rb")
            return self._read_reply(f)

    def ping(self) -> None:
        if self.command("PING") != "PONG":
            raise RedisError("Redis PING did not return PONG")

    def hset(self, key: str, fields: dict[str, object]) -> None:
        parts: list[object] = ["HSET", key]
        for name, value in fields.items():
            parts.extend((name, value))
        self.command(*parts)

    def expire(self, key: str, seconds: int) -> None:
        self.command("EXPIRE", key, seconds)

    def hgetall(self, key: str) -> dict[str, str]:
        values = self.command("HGETALL", key)
        if values is None:
            return {}
        if not isinstance(values, list) or len(values) % 2:
            raise RedisError("malformed HGETALL reply")
        return {str(values[i]): str(values[i + 1]) for i in range(0, len(values), 2)}

    def zrange(self, key: str, start: int, stop: int) -> list[str]:
        values = self.command("ZRANGE", key, start, stop)
        if values is None:
            return []
        if not isinstance(values, list):
            raise RedisError("malformed ZRANGE reply")
        return [str(value) for value in values]

    def zadd(self, key: str, score: int | float, member: str) -> None:
        self.command("ZADD", key, score, member)

    def zrem(self, key: str, member: str) -> None:
        self.command("ZREM", key, member)


@dataclass(frozen=True)
class Activation:
    call_key: str
    job_key: str
    runtime_keys: list[str]
    instruction_keys: list[str]


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def activate_call(client: RedisClient, call_identity: str, call: dict) -> Activation:
    client.ping()
    call_key = f"call:{call_identity}:record"
    source = call["source"]
    plan = call["plan"]
    client.hset(call_key, {
        "identity": call_identity,
        "schema": call["schema"],
        "created_at": call["created_at"],
        "source_identity": f"{source['repo_name']}:{source['commit']}",
        "content": _json(call),
        "extra_json": _json({"source_ref": source.get("ref"), "plan_ref": plan["ref"]}),
    })
    client.expire(call_key, CALL_TTL)

    all_instruction_keys: list[str] = []
    runtime_keys: list[str] = []
    steps = plan.get("steps") or []
    total_steps = len(steps)
    for step in steps:
        ordinal = int(step["position"])
        step_instruction_keys: list[str] = []
        for instruction in step.get("instructions") or []:
            position = int(instruction["position"])
            key = f"instruction:{call_identity}:{ordinal}:{position}"
            client.hset(key, {
                "call_identity": call_identity,
                "step_ordinal": ordinal,
                "position": position,
                "id": instruction["id"],
                "ref": instruction["ref"],
                "label": instruction["label"],
                "kind": instruction["kind"],
                "body": instruction["body"],
            })
            client.expire(key, INSTRUCTION_TTL)
            step_instruction_keys.append(key)
            all_instruction_keys.append(key)

        runtime_key = f"runtime:{call_identity}:{ordinal}"
        executor = step["executor"]
        client.hset(runtime_key, {
            "identity": runtime_key,
            "ordinal": ordinal,
            "label": step["label"],
            "plan_identity": plan["id"],
            "engine": executor,
            "engine_kind": "llm" if executor == "chatgpt" else executor,
            "model": step["entrypoint"],
            "instruction_keys": _json(step_instruction_keys),
            "total_steps": total_steps,
        })
        client.expire(runtime_key, RUNTIME_TTL)
        runtime_keys.append(runtime_key)

    job_key = f"job:{call_identity}:record"
    client.hset(job_key, {
        "identity": call_identity,
        "plan_identity": plan["id"],
        "total_steps": total_steps,
        "created_at": call["created_at"],
        "result_ordinal_hint": "",
        "task_ordinal_hint": "",
        "task_created_at_hint": "",
    })
    client.zadd(ACTIVE_KEY, 0, job_key)
    return Activation(call_key, job_key, runtime_keys, all_instruction_keys)
