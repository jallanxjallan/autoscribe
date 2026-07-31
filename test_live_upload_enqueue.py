"""Live upload/enqueue integration test that leaves Redis populated.

Run from the AutoScribe repository root:

    pytest -q -s test_live_upload_enqueue.py

This test invokes the installed ``asc`` CLI and writes to the configured Redis
instance. It intentionally performs no cleanup. Inspect the printed keys, then
flush Redis manually when finished.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Iterable, Mapping
from typing import Any

import pytest
import redis


PLAN_SLUG = "plan.pytest-upload-enqueue.ghi789"
ROLE_SLUG = "rol.pytest-editor.abc123"
SPECIFIC_SLUG = "spc.pytest-cleanup.def456"

FIRST_CALL_SLUGS = (
    "cnt.pytest-first.jkl012",
    "prv.pytest-compilation.mno345",
)
SECOND_CALL_SLUGS = (
    "cnt.pytest-second.pqr678",
    "prv.pytest-external.stu901",
)
ALL_TEST_SLUGS = (ROLE_SLUG, SPECIFIC_SLUG, PLAN_SLUG, *FIRST_CALL_SLUGS, *SECOND_CALL_SLUGS)


def ndjson(records: Iterable[Mapping[str, Any]]) -> str:
    return "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)


def run_asc(asc: str, *args: str, records: Iterable[Mapping[str, Any]]) -> subprocess.CompletedProcess[str]:
    payload = ndjson(records)
    completed = subprocess.run(
        [asc, *args],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
        env=os.environ.copy(),
    )
    print(f"\n$ {asc} {' '.join(args)}")
    print(payload, end="")
    if completed.stdout:
        print("stdout:")
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print("stderr:")
        print(completed.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    assert completed.returncode == 0, (
        f"command failed ({completed.returncode}): {asc} {' '.join(args)}\n"
        f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    return completed


def redis_client() -> redis.Redis:
    url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    client = redis.Redis.from_url(url, decode_responses=True)
    try:
        client.ping()
    except redis.RedisError as exc:
        pytest.fail(f"Redis is unavailable at {url}: {exc}")
    return client


def read_key(client: redis.Redis, key: str) -> Any:
    key_type = client.type(key)
    if key_type == "hash":
        return client.hgetall(key)
    if key_type == "zset":
        return client.zrange(key, 0, -1, withscores=True)
    if key_type == "list":
        return client.lrange(key, 0, -1)
    if key_type == "set":
        return sorted(client.smembers(key))
    if key_type == "string":
        return client.get(key)
    if key_type == "stream":
        return client.xrange(key)
    return f"<unsupported Redis type: {key_type}>"


def print_key(client: redis.Redis, key: str) -> None:
    key_type = client.type(key)
    ttl = client.ttl(key)
    value = read_key(client, key)
    print(f"\n{key}  type={key_type} ttl={ttl}")
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def upload_records() -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    instructions = [
        {
            "type": "instruction",
            "identity": ROLE_SLUG,
            "content": "Act as a careful mechanical editor.",
            "extra": {"filename_hint": "Pytest Role.md"},
        },
        {
            "type": "instruction",
            "identity": SPECIFIC_SLUG,
            "content": "Clean punctuation and spacing without changing meaning.",
            "extra": {"filename_hint": "Pytest Cleanup.md"},
        },
    ]

    plan = {
        "type": "plan",
        "identity": PLAN_SLUG,
        "content": {
            "label": "Pytest upload/enqueue inspection",
            "steps": {
                "1": {
                    "label": "Mock local step",
                    "engine": "local",
                    "engine_kind": "script",
                    "script": "pytest.mock_transform",
                    "instruction_slugs": {
                        "role": [ROLE_SLUG],
                        "specifics": [SPECIFIC_SLUG],
                    },
                }
            },
        },
        "extra": {"test_run": "live-upload-enqueue"},
    }

    first_calls = [
        {
            "type": "call",
            "identity": FIRST_CALL_SLUGS[0],
            "content": "---\nslug: cnt.pytest-first.jkl012\n---\n\nFirst live pytest call.\n",
            "extra": {"filename_hint": "Pytest First.md"},
        },
        {
            "type": "call",
            "identity": FIRST_CALL_SLUGS[1],
            "content": "Compiled source A.\n\nCompiled source B.\n",
            "extra": {
                "filename_hint": "Pytest Compilation.md",
                "source_paths": ["Notes/A.md", "Notes/B.md"],
            },
        },
    ]

    second_calls = [
        {
            "type": "call",
            "identity": SECOND_CALL_SLUGS[0],
            "content": "---\nslug: cnt.pytest-second.pqr678\n---\n\nSecond live pytest call.\n",
            "extra": {"filename_hint": "Pytest Second.md"},
        },
        {
            "type": "call",
            "identity": SECOND_CALL_SLUGS[1],
            "content": "Imported external text for live pytest inspection.\n",
            "extra": {"filename_hint": "Pytest External.docx"},
        },
    ]
    return instructions, plan, first_calls, second_calls


def manifest_for(call_slugs: Iterable[str]) -> list[dict[str, str]]:
    return [{"call": call_slug, "plan": PLAN_SLUG} for call_slug in call_slugs]


def test_live_uploads_and_enqueue_materialize_redis_keys() -> None:
    """Perform both requested runs and leave all resulting Redis keys intact."""

    asc = shutil.which("asc")
    if asc is None:
        pytest.fail("Could not find the asc executable in PATH")

    client = redis_client()
    before = set(client.scan_iter(match="*"))
    instructions, plan, first_calls, second_calls = upload_records()

    print("\n=== RUN 1: instructions, plan, calls, manifest ===")
    run_asc(asc, "upload", "instructions", records=instructions)
    run_asc(asc, "upload", "plans", records=[plan])
    run_asc(asc, "upload", "calls", records=first_calls)
    run_asc(asc, "enqueue", records=manifest_for(FIRST_CALL_SLUGS))

    print("\n=== RUN 2: other calls and manifest only ===")
    run_asc(asc, "upload", "calls", records=second_calls)
    run_asc(asc, "enqueue", records=manifest_for(SECOND_CALL_SLUGS))

    slugmap = client.hgetall("state:slugmap:index")
    missing_slugs = [slug for slug in ALL_TEST_SLUGS if slug not in slugmap]
    assert not missing_slugs, f"missing slugmap entries: {missing_slugs}"

    for slug in ALL_TEST_SLUGS:
        key = slugmap[slug]
        assert client.exists(key), f"slugmap target does not exist: {slug} -> {key}"

    after = set(client.scan_iter(match="*"))
    created = sorted(after - before)

    print("\n=== TEST SLUGMAP ENTRIES ===")
    for slug in ALL_TEST_SLUGS:
        print(f"{slug} -> {slugmap[slug]}")

    print("\n=== KEYS CREATED DURING THIS TEST ===")
    if created:
        for key in created:
            print_key(client, key)
    else:
        print("No entirely new key names were detected; existing test slugs may have been overwritten.")

    print("\n=== CURRENT RECORDS REFERENCED BY TEST SLUGS ===")
    for key in sorted({slugmap[slug] for slug in ALL_TEST_SLUGS}):
        print_key(client, key)

    print("\n=== SHARED INDEX / QUEUE KEYS ===")
    for key in sorted(after):
        if key == "state:slugmap:index" or key.startswith(("active:", "queue:", "jobs:", "job:")):
            print_key(client, key)

    print("\nRedis was intentionally not cleaned up.")
    print("Flush it manually after inspection.")
